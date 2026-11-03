"""Round stamp detection: shape first, colour second, no templates."""
import unittest

from local_dependencies import activate_local_dependencies
activate_local_dependencies()
import cv2
import numpy as np
from PIL import Image
from arar.models import ROOT
from arar.stamps import find_stamps

DPI = 150
PAPER = (241, 240, 247)  # scanner paper is slightly bluish


def page():
    return np.full((900, 700, 3), PAPER, np.uint8)


def draw_stamp(image, centre, colour, radius=30, thickness=2, arc=360):
    """A QA-style stamp: thin outer ring with lines of text inside, in the same ink."""
    cv2.ellipse(image, centre, (radius, radius), 0, 0, arc, colour, thickness, cv2.LINE_AA)
    x, y = centre
    for dy, text in ((-11, 'QA-2'), (2, 'RECVNG'), (14, '025')):
        size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, .32, thickness)[0]
        cv2.putText(image, text, (x - size[0] // 2, y + dy), cv2.FONT_HERSHEY_SIMPLEX, .32, colour, thickness, cv2.LINE_AA)
    return image


def kinds(image, **kwargs):
    return sorted(s.kind for s in find_stamps(image, DPI, **kwargs))


class StampTests(unittest.TestCase):
    def test_colour_is_classified_after_the_shape(self):
        for colour, normal, as_blue in (((45, 120, 205), 'blue', 'blue'),      # RGB: strong blue ink
                                        ((50, 48, 46), 'black', 'black'),
                                        ((212, 208, 238), 'faint', 'blue'),    # pale blue: option applies
                                        ((190, 190, 190), 'faint', 'faint')):  # pale grey: never blue
            with self.subTest(colour=colour):
                image = draw_stamp(page(), (350, 450), colour)
                self.assertEqual(kinds(image), [normal])
                self.assertEqual(kinds(image, faint_blue_as_blue=True), [as_blue])

    def test_blue_writing_dates_letters_and_tables_are_not_stamps(self):
        image = page()
        blue = (40, 90, 200)
        # Handwriting and a date stamp in blue ink.
        cv2.putText(image, 'Hayati Gelik', (60, 120), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.4, blue, 2, cv2.LINE_AA)
        cv2.putText(image, '02 OCT 2026', (60, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.1, blue, 2, cv2.LINE_AA)
        cv2.putText(image, 'N/A  351', (380, 220), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.6, blue, 2, cv2.LINE_AA)
        # A bold logo letter and printed text.
        cv2.putText(image, 'onsemi', (60, 360), cv2.FONT_HERSHEY_DUPLEX, 3, (40, 40, 60), 9, cv2.LINE_AA)
        # A dense table / chart grid.
        for x in range(60, 640, 22):
            cv2.line(image, (x, 450), (x, 820), (30, 30, 30), 1)
        for y in range(450, 830, 22):
            cv2.line(image, (60, y), (640, y), (30, 30, 30), 1)
        self.assertEqual(find_stamps(image, DPI), [])

    def test_stamp_over_writing_and_rules_is_still_found(self):
        image = page()
        cv2.line(image, (100, 450), (600, 450), (30, 30, 30), 2)
        cv2.line(image, (330, 300), (330, 600), (30, 30, 30), 2)
        cv2.putText(image, 'Signature / Stamp', (240, 455), cv2.FONT_HERSHEY_SIMPLEX, .6, (20, 20, 20), 1, cv2.LINE_AA)
        draw_stamp(image, (350, 450), (40, 100, 210))
        self.assertEqual(kinds(image), ['blue'])

    def test_partial_ring_follows_the_sensitivity_setting(self):
        image = draw_stamp(page(), (350, 450), (150, 175, 230), arc=200)
        self.assertEqual(kinds(image), ['blue'])
        self.assertEqual(kinds(image, sensitivity=1.3), [])     # a stricter setting

    def test_barcode_boxes_are_excluded(self):
        image = draw_stamp(page(), (350, 450), (40, 40, 40))
        self.assertEqual(kinds(image), ['black'])
        self.assertEqual(kinds(image, exclude=[(300, 400, 400, 500)]), [])

    def test_supplied_stamp_images_keep_their_colour(self):
        for name, expected in (('stamp_blue_1.png', 'blue'), ('stamp_blue_2.png', 'blue'), ('stamp_blue_3.png', 'blue'),
                               ('stamp_blue_4.png', 'blue'), ('stamp_blue_5.png', 'blue'),
                               ('stamp_black.png', 'black'), ('stamp_faint.png', 'faint')):
            with self.subTest(name=name):
                stamp = Image.open(ROOT / 'assets' / name).convert('RGB')
                width = 110  # about 19 mm at 150 dpi, a ring of about 10 mm
                stamp = stamp.resize((width, round(width * stamp.height / stamp.width)), Image.Resampling.LANCZOS)
                image = Image.fromarray(page())
                image.paste(stamp, (300, 400))
                self.assertEqual(kinds(np.asarray(image)), [expected])

    def test_each_stamp_is_reported_once(self):
        image = draw_stamp(page(), (200, 300), (40, 100, 210))
        draw_stamp(image, (480, 650), (45, 45, 45))
        found = find_stamps(image, DPI)
        self.assertEqual(sorted(s.kind for s in found), ['black', 'blue'])
        for stamp in found:
            x0, y0, x1, y1 = stamp.box
            self.assertTrue(20 < x1 - x0 < 100 and 20 < y1 - y0 < 100)

    def test_cancel_stops_without_results(self):
        import threading
        stop = threading.Event()
        stop.set()
        self.assertEqual(find_stamps(draw_stamp(page(), (350, 450), (40, 100, 210)), DPI, cancel=stop), [])


if __name__ == '__main__':
    unittest.main()
