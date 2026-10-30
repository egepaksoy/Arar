"""Cached correlation must retain locations/scores and isolate page data."""
import unittest
from unittest.mock import patch
from local_dependencies import activate_local_dependencies
activate_local_dependencies()
import numpy as np
from arar.detection import _PageCorrelation, _PreparedTemplate, _template_peak


def direct_peak(page, template):
    h,w=template.shape
    centered=template-template.mean()
    scores=np.zeros((page.shape[0]-h+1,page.shape[1]-w+1))
    for y,x in np.ndindex(scores.shape):
        crop=page[y:y+h,x:x+w]
        crop=crop-crop.mean()
        norm=np.linalg.norm(crop)*np.linalg.norm(centered)
        if norm>1e-6:
            scores[y,x]=np.sum(crop*centered)/norm
    y,x=np.unravel_index(np.argmax(scores),scores.shape)
    return scores[y,x],(x,y)


class StampCacheTests(unittest.TestCase):
    def test_shared_templates_keep_scores_and_positions_across_pages_and_fft_sizes(self):
        rng=np.random.default_rng(123)
        templates=[rng.random(size) for size in ((3,4),(7,8),(5,6),(3,4))]
        prepared=[_PreparedTemplate(t) for t in templates]
        for shape in ((12,13),(19,21)):
            page=rng.random(shape)
            context=_PageCorrelation(page)
            for template,ready in zip(templates,prepared):
                with self.subTest(page=shape,template=template.shape):
                    expected,position=direct_peak(page,template)
                    score,found=_template_peak(context,ready)
                    self.assertEqual(found,position)
                    self.assertAlmostEqual(score,expected,places=11)

    def test_page_pixels_are_reused_for_all_templates(self):
        rng=np.random.default_rng(456)
        context=_PageCorrelation(rng.random((40,40)))
        from arar.detection import cv2
        with patch('arar.detection.cv2.matchTemplate',wraps=cv2.matchTemplate) as match:
            for size in ((5,5),(7,9),(10,10)):
                _template_peak(context,_PreparedTemplate(rng.random(size)))
        self.assertEqual(match.call_count,3)
        self.assertTrue(all(call.args[0] is context.pixels for call in match.call_args_list))

    def test_near_threshold_score_is_rescored_in_double_precision(self):
        rng=np.random.default_rng(789)
        template=rng.random((12,14))
        noise=rng.random(template.shape)
        page=.7*template+.3*noise
        expected,position=direct_peak(page,template)
        score,found=_template_peak(page,template)
        self.assertEqual(found,position)
        self.assertAlmostEqual(score,expected,places=12)
        self.assertGreater(score,expected-1e-10)
        self.assertLess(score,expected+1e-10)

    def test_constant_and_oversized_templates_remain_no_match(self):
        page=_PageCorrelation(np.zeros((12,13)))
        for template in (np.ones((4,4)),np.ones((14,14))):
            self.assertEqual(_template_peak(page,_PreparedTemplate(template)),(0.,(0,0)))
        score,_=_template_peak(page,_PreparedTemplate(np.arange(16).reshape(4,4)))
        self.assertEqual(score,0.)

    def test_blank_background_cannot_beat_a_real_stamp(self):
        rng=np.random.default_rng(42)
        template=rng.random((37,46))
        page=np.zeros((320,270))
        page[210:247,170:216]=template
        score,position=_template_peak(page,template)
        self.assertEqual(position,(170,210))
        self.assertAlmostEqual(score,1.,places=10)


if __name__=='__main__':
    unittest.main()
