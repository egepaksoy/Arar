"""Round stamp detection on page images, independent of stamp templates.

A stamp is found by its shape first: a thin ring that is complete, stands out
from its surroundings and has text inside. Only then is its ink colour
classified. Blue handwriting, date stamps and printed text are not rings, so
they are not stamps; black stamps are found the same way as blue ones.
"""
from dataclasses import dataclass

import cv2
import numpy as np

WORK_DPI = 100          # Ring geometry is measured at this resolution.
MIN_RADIUS_MM = 3.5     # Stamps are roughly 8-30 mm across.
MAX_RADIUS_MM = 15
MIN_RING_MM = 4.0       # Measured ring radius: QA stamps are 4.4 mm and up; circled
                        # digits, icons, logos and the '0' of a date stamp are smaller.
BLUE_EXCESS = 27        # Median blue-over-red excess of blue stamp ink.
PALE_DARKNESS = 60      # Below this darkness a bluish stamp is a pale one.
BLACK_DARKNESS = 70     # Neutral ink at least this dark is black.


@dataclass(frozen=True)
class Stamp:
    kind: str                       # 'blue', 'faint' or 'black'
    box: tuple[float, float, float, float]   # image pixels
    confidence: float
    pale_blue: bool = False         # a faint stamp whose ink is still blue


def _planes(rgb):
    """Ink darkness, neutral darkness and blue excess against the local paper."""
    small = cv2.resize(rgb, None, fx=.125, fy=.125, interpolation=cv2.INTER_AREA)
    paper = cv2.medianBlur(cv2.dilate(small, np.ones((7, 7), np.uint8)), 5)
    paper = cv2.resize(paper, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_LINEAR).astype(np.int16)
    pixels = rgb.astype(np.int16)
    ink = np.clip((paper - pixels).max(axis=2), 0, 255).astype(np.uint8)
    dark = np.clip(paper.mean(axis=2) - pixels.mean(axis=2), 0, 255)
    excess = (pixels[:, :, 2] - pixels[:, :, 0]) - (paper[:, :, 2] - paper[:, :, 0])
    return ink, dark, excess


def _ring_features(mask, cx, cy, r):
    """Measure a candidate ring in polar coordinates (rows: angle, columns: radius)."""
    bins, angles = 64, 120
    outer = r * 1.6
    polar = cv2.warpPolar(mask.view(np.uint8) * 255, (bins, angles), (float(cx), float(cy)), outer,
                          cv2.WARP_POLAR_LINEAR | cv2.INTER_NEAREST) > 0
    step = outer / bins
    near = polar.copy()
    near[:, 1:] |= polar[:, :-1]
    near[:, :-1] |= polar[:, 1:]
    coverage = near.mean(axis=0)
    low, high = int(r * .7 / step), min(bins - 2, int(r * 1.25 / step))
    ring = low + int(np.argmax(coverage[low:high + 1]))
    ring_r = ring * step
    o0, o1 = int((ring_r + .18 * r) / step), min(bins, int((ring_r + .5 * r) / step) + 1)
    i0 = int(.2 * r / step)
    i1 = max(i0 + 1, int((ring_r - .2 * r) / step))
    surround = float(coverage[o0:o1].mean()) if o1 > o0 else 1.
    # Thickness: neighbouring radii covered nearly as well as the ring itself.
    strong = coverage >= coverage[ring] * .8
    lo = hi = ring
    while lo > 0 and strong[lo - 1]:
        lo -= 1
    while hi < bins - 1 and strong[hi + 1]:
        hi += 1
    hit = near[:, max(0, ring - 1):ring + 2].any(axis=1)
    sectors = int((hit.reshape(8, -1).mean(axis=1) >= .25).sum())
    # Arc continuity: covered angles on runs of at least 15 degrees. Straight
    # table and grid lines only cross the ring in short isolated runs.
    if hit.all():
        arcs = 1.
    else:
        rolled = np.roll(hit, -int(np.argmin(hit)))
        edges = np.flatnonzero(np.diff(np.r_[0, rolled.astype(int), 0]))
        runs = edges[1::2] - edges[::2]
        arcs = float(runs[runs >= 5].sum() / max(1, hit.sum()))
    return dict(cover=float(coverage[ring]), radius=float(ring_r), prominence=float(coverage[ring] - surround),
                interior=float(polar[:, i0:i1].mean()), thickness=(hi - lo + 1) * step / r,
                sectors=sectors, arcs=arcs)


def _ink_colour(rgb, cx, cy, r):
    """Colour, outline stroke and number of ink parts inside the ring, at full resolution.

    Returns None without ink, else (kind, stroke, parts).
    """
    h, w = rgb.shape[:2]
    pad = int(r * 1.6)
    x0, x1, y0, y1 = max(0, int(cx - pad)), min(w, int(cx + pad)), max(0, int(cy - pad)), min(h, int(cy + pad))
    crop = rgb[y0:y1, x0:x1].astype(np.float32)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    dist = np.hypot(xx - cx, yy - cy)
    around = dist > r * 1.25
    paper = np.percentile(crop[around] if around.sum() > 50 else crop.reshape(-1, 3), 90, axis=0)
    darkness = paper.mean() - crop.mean(axis=2)
    candidate = (dist <= r * 1.05) & (darkness > 12)
    if candidate.sum() < 20:
        return None
    threshold = np.percentile(darkness[candidate], 60)
    strongest = crop[candidate & (darkness >= threshold)]
    excess = (strongest[:, 2] - strongest[:, 0]) - (paper[2] - paper[0])
    dark = float(np.median(paper.mean() - strongest.mean(axis=1)))
    blue_share = float((excess >= 18).mean())
    # Stamps have a thin outline; a bold letter 'O' has a stroke that is a
    # large part of its radius.
    band = (dist >= r * .8) & (dist <= r * 1.2) & (darkness > max(12, threshold * .6))
    distance = cv2.distanceTransform(band.astype(np.uint8), cv2.DIST_L2, 3)
    stroke = float(np.percentile(distance[band], 90) * 2 / r) if band.sum() > 10 else 1.
    # A stamp has lines of text inside its ring; a circled digit, a drawn hole
    # or a printed icon has one or two shapes.
    channel = (paper - crop).max(axis=2)
    level = max(12., float(np.percentile(channel[dist <= r * 1.05], 85)) * .45)
    inner = ((channel >= level) & (dist <= r * .72)).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(inner, connectivity=8)
    parts = int((stats[1:count, cv2.CC_STAT_AREA] >= max(3, (r * .04) ** 2)).sum())
    if blue_share >= .5 and float(np.median(excess)) >= BLUE_EXCESS:
        kind = 'blue'
    elif blue_share >= .5 and dark < PALE_DARKNESS:
        kind = 'pale_blue'   # dark navy print is treated as neutral below
    elif dark >= BLACK_DARKNESS:
        kind = 'black'
    else:
        kind = 'faint'
    return kind, stroke, parts


def _evaluate(masks, counts, cx, cy, r, s, min_radius, from_patch=False):
    """Best ring reading of a circle over the ink masks: (plausible, score, features).

    from_patch: the circle was drawn around a square patch of blue ink, which
    a smudged stamp gives but a printed band or table header does not.
    """
    h, w = masks[0].shape
    x0, y0 = max(0, int(cx - r * 1.2)), max(0, int(cy - r * 1.2))
    x1, y1 = min(w, int(cx + r * 1.2) + 1), min(h, int(cy + r * 1.2) + 1)
    best = None
    for index, mask in enumerate(masks):
        if index:
            total = counts[index - 1]
            present = total[y1, x1] - total[y0, x1] - total[y1, x0] + total[y0, x0]
            if present < 2 * np.pi * r * .4:
                continue   # too little of this ink to draw a ring
        ft = _ring_features(mask, cx, cy, r)
        plausible = (ft['cover'] >= .45 * s and ft['prominence'] >= .42 * s and ft['arcs'] >= .55
                     and ft['sectors'] >= 5 and .15 <= ft['interior'] <= .9 and ft['radius'] >= min_radius)
        if plausible and ft['thickness'] > .35:
            # Ink right inside the ring (smudged stamps, text set close to the
            # outline) reads as a thick ring; accept it only around a patch of
            # blue ink and with a ring that goes most of the way round. The
            # colour step below rejects thick neutral letters.
            plausible = from_patch and index < 2 and ft['cover'] >= .6 and ft['sectors'] >= 7
        score = ft['prominence'] + ft['cover'] * .5
        if best is None or (plausible, score) > (best[0], best[1]):
            best = (plausible, score, ft)
        if index == 0 and (ft['cover'] < .3 or plausible):
            break   # no ring at all, or the plain ink mask already shows it
    return best


def _blue_blobs(mask, mm):
    """Circles around stamp-sized patches of blue ink.

    A smudged or doubled stamp can give Hough a poor centre; the patch of its
    ink gives a second starting point.
    """
    joined = cv2.morphologyEx(mask.view(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(1.5 * mm) | 1,) * 2))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    circles = []
    for x, y, w, h, area in stats[1:count]:
        r = max(w, h) / 2
        if MIN_RADIUS_MM * mm <= r <= MAX_RADIUS_MM * mm and .6 <= w / h <= 1.6:
            circles.append((x + w / 2, y + h / 2, r))
    return circles


def find_stamps(rgb, dpi, *, exclude=(), faint_blue_as_blue=False, sensitivity=1., cancel=None):
    """Return the round stamps on an RGB page image (numpy array, ``dpi`` resolution).

    exclude: image-pixel boxes (barcodes) whose bars must not count as a ring.
    sensitivity: 1 is the default; lower values accept weaker rings.
    """
    factor = min(1., WORK_DPI / dpi)
    work = cv2.resize(rgb, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor < 1 else rgb
    mm = dpi * factor / 25.4
    ink, dark, excess = _planes(work)
    circles = cv2.HoughCircles(cv2.GaussianBlur(ink, (0, 0), 1.), cv2.HOUGH_GRADIENT_ALT, dp=1.2,
                               minDist=int(MIN_RADIUS_MM * mm), param1=40, param2=.45,
                               minRadius=int(MIN_RADIUS_MM * mm), maxRadius=int(MAX_RADIUS_MM * mm))
    masks = (ink >= 22, (excess >= 18) & (ink >= 15), (dark >= 45) & (excess < 18))
    # Pixel counts per mask in any box, so a colour mask is only measured
    # where that ink is actually present (pages of charts give many circles).
    counts = [cv2.integral(mask.view(np.uint8)) for mask in masks[1:]]
    candidates = [(*c, False) for c in circles[0]] if circles is not None else []
    candidates += [(*c, True) for c in _blue_blobs(masks[1], mm)]
    s = sensitivity
    found = []
    for cx, cy, r, from_patch in candidates:
        if cancel is not None and cancel.is_set():
            return []
        if any(x0 <= cx / factor <= x1 and y0 <= cy / factor <= y1 for x0, y0, x1, y1 in exclude):
            continue
        plausible, score, ft = _evaluate(masks, counts, cx, cy, r, s, MIN_RING_MM * mm, from_patch)
        if not plausible:
            continue
        px, py = cx / factor, cy / factor
        radius = (ft['radius'] or r) / factor
        colour = _ink_colour(rgb, px, py, radius)
        if colour is None:
            continue
        kind, stroke, parts = colour
        if kind not in ('blue', 'pale_blue'):
            # Neutral ink is everywhere in print, so a neutral ring must be
            # nearly complete, clearly isolated, thin and hold several parts
            # of text (drawn circles, circled digits and icons do not).
            if not (ft['cover'] >= min(1., .8 * s) and ft['prominence'] >= .45 * s and ft['arcs'] >= .8
                    and ft['sectors'] >= 7 and stroke <= .2 and parts >= 3):
                continue
        confidence = float(min(1., .5 * min(1., ft['prominence'] / .6) + .3 * ft['cover'] + .2 * ft['arcs']))
        pale = kind == 'pale_blue'
        kind = 'blue' if pale and faint_blue_as_blue else 'faint' if pale else kind
        found.append((score, Stamp(kind, (px - radius, py - radius, px + radius, py + radius), confidence, pale)))
    # Overlapping circles describe the same stamp: keep the strongest.
    found.sort(key=lambda item: item[0], reverse=True)
    kept = []
    for _, stamp in found:
        cx, cy = (stamp.box[0] + stamp.box[2]) / 2, (stamp.box[1] + stamp.box[3]) / 2
        r = (stamp.box[2] - stamp.box[0]) / 2
        if any(np.hypot(cx - (k.box[0] + k.box[2]) / 2, cy - (k.box[1] + k.box[3]) / 2)
               < max(r, (k.box[2] - k.box[0]) / 2) * .8 for k in kept):
            continue
        kept.append(stamp)
    return kept
