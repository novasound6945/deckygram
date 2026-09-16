"""The two clip controls: how many bits a second, and how many frames.

They are deliberately independent. The bitrate is used exactly as
picked - scaling it by the frame rate would make the label a lie - while
the frame rate decides how many pictures those bits cover, and so when a
clip stops being worth sending at all.
"""

import os
import tempfile
import unittest

from . import context  # noqa: F401
from deckygram import destinations, discord, media, tg

TG = {"token": "123:AA", "chat_id": "42"}
DC = {"destination": "discord",
      "webhook_url": "https://discord.com/api/webhooks/1/tok"}


def dest(**over):
    return destinations.build(dict(TG, **over))


class TestPickBitrate(unittest.TestCase):
    def test_an_offered_number_is_taken(self):
        self.assertEqual(media.pick_bitrate(7_500_000), 7_500_000)

    def test_strings_from_json_settings_are_fine(self):
        self.assertEqual(media.pick_bitrate("6000000"), 6_000_000)

    def test_send_as_recorded_is_a_choice_of_its_own(self):
        self.assertEqual(media.pick_bitrate(media.SOURCE), media.SOURCE)

    def test_a_number_we_do_not_offer_falls_back(self):
        self.assertEqual(media.pick_bitrate(7_777_777), media.DEFAULT_BITRATE)

    def test_nothing_chosen_is_the_default(self):
        # Not "as recorded": an absent setting must not be read as the
        # most generous option going.
        self.assertEqual(media.pick_bitrate(None), media.DEFAULT_BITRATE)
        self.assertEqual(media.pick_bitrate(""), media.DEFAULT_BITRATE)

    def test_old_presets_are_translated(self):
        self.assertEqual(media.pick_bitrate(None, "quality"), media.SOURCE)
        self.assertEqual(media.pick_bitrate(None, "balanced"), 6_000_000)
        self.assertEqual(media.pick_bitrate(None, "reach"), 3_750_000)

    def test_an_unknown_preset_is_the_default(self):
        self.assertEqual(media.pick_bitrate(None, "nonsense"),
                         media.DEFAULT_BITRATE)

    def test_a_real_choice_beats_an_old_preset(self):
        self.assertEqual(media.pick_bitrate(3_750_000, "quality"), 3_750_000)

    def test_every_offered_value_is_accepted(self):
        for b in media.BITRATES:
            self.assertEqual(media.pick_bitrate(b), b)

    def test_the_default_is_what_a_minute_can_use(self):
        # 45 MB over 60 s is ~6.2 Mbit/s, so 6 is the point where the
        # choice and the limit agree.
        fit = media.fit_bitrate(tg.SIZE_TARGET, 60, media.DEFAULT_BITRATE)
        self.assertEqual(fit, media.DEFAULT_BITRATE)


class TestFloor(unittest.TestCase):
    def test_thirty_is_the_baseline(self):
        self.assertEqual(media.floor_for(30), media.FLOOR)

    def test_sixty_doubles_it(self):
        self.assertEqual(media.floor_for(60), media.FLOOR * 2)

    def test_unknown_is_the_baseline(self):
        self.assertEqual(media.floor_for(0), media.FLOOR)


class TestDestination(unittest.TestCase):
    def test_the_bitrate_is_used_as_picked(self):
        # Not scaled by the frame rate: the dropdown says 7.5 Mbps, so
        # 7.5 Mbps is what the encoder is asked for.
        for fps in (30, 60):
            args = dest(clip_bitrate=7_500_000, video_fps=fps).encode_args()
            self.assertEqual(args["bitrate"], 7_500_000)

    def test_the_frame_rate_is_passed_through(self):
        self.assertEqual(dest(video_fps=60).encode_args()["fps"], 60)

    def test_the_frame_height_defaults_to_the_decks_own_screen(self):
        self.assertEqual(dest().encode_args()["maxh"], media.DEFAULT_HEIGHT)

    def test_a_chosen_height_is_used(self):
        self.assertEqual(dest(clip_height=480).encode_args()["maxh"], 480)

    def test_a_height_we_do_not_offer_falls_back(self):
        self.assertEqual(dest(clip_height=1080).encode_args()["maxh"],
                         media.DEFAULT_HEIGHT)

    def test_discord_never_goes_above_its_own_cap(self):
        d = destinations.build(dict(DC, clip_height=800))
        self.assertEqual(d.encode_args()["maxh"], discord.HEIGHT_CAP)

    def test_discord_honours_a_lower_choice(self):
        # Its cap is a limit, not a target.
        d = destinations.build(dict(DC, clip_height=480))
        self.assertEqual(d.encode_args()["maxh"], 480)

    def test_discord_still_brings_the_frame_down(self):
        # A fifth of the budget: 1280x800 at ~1.1 Mbit/s would smear.
        d = destinations.build(dict(DC, clip_bitrate=10_000_000))
        self.assertEqual(d.encode_args()["maxh"], discord.HEIGHT_CAP)

    def test_sixty_shortens_the_longest_clip(self):
        self.assertLess(dest(video_fps=60).max_clip_seconds(),
                        dest(video_fps=30).max_clip_seconds())

    def test_the_longest_clip_does_not_depend_on_the_bitrate(self):
        # The give-up point is about what is watchable, not about what
        # was asked for.
        self.assertEqual(dest(clip_bitrate=media.SOURCE).max_clip_seconds(),
                         dest(clip_bitrate=3_750_000).max_clip_seconds())

    def test_old_settings_still_work(self):
        self.assertEqual(dest(clip_preset="quality").encode_args()["bitrate"],
                         media.SOURCE)


class TestEstimate(unittest.TestCase):
    def test_a_minute_at_six_fits(self):
        e = dest(clip_bitrate=6_000_000).estimate(60)
        self.assertTrue(e["fits"])
        self.assertTrue(e["sendable"])
        self.assertLessEqual(e["mb"], tg.BOT_LIMIT / 1024 / 1024)

    def test_a_minute_at_the_top_of_the_ladder_does_not(self):
        # 7.5 Mbit/s for a minute is ~55 MB against Telegram's 50.
        e = dest(clip_bitrate=7_500_000).estimate(60)
        self.assertFalse(e["fits"])
        self.assertGreater(e["asked_mb"], 50)

    def test_what_actually_goes_out_is_reported(self):
        e = dest(clip_bitrate=7_500_000).estimate(60)
        self.assertLess(e["bitrate"], 7_500_000)
        self.assertLessEqual(e["mb"], tg.BOT_LIMIT / 1024 / 1024)
        self.assertTrue(e["sendable"])

    def test_a_short_clip_keeps_the_whole_choice(self):
        e = dest(clip_bitrate=7_500_000).estimate(20)
        self.assertTrue(e["fits"])
        self.assertEqual(e["bitrate"], 7_500_000)

    def test_as_recorded_quotes_no_length(self):
        # There is no ceiling of ours to overrun, so how long a clip
        # survives intact is Steam's to decide, not ours to claim.
        e = dest(clip_bitrate=media.SOURCE).estimate(60)
        self.assertTrue(e["source"])
        self.assertNotIn("full_seconds", e)
        self.assertTrue(e["sendable"])

    def test_as_recorded_still_respects_the_limit(self):
        e = dest(clip_bitrate=media.SOURCE).estimate(60)
        self.assertLessEqual(
            (e["bitrate"] + media.AUDIO_BITRATE) * 60 / 8, tg.SIZE_TARGET)

    def test_a_numbered_choice_says_it_is_not_the_source_one(self):
        self.assertFalse(dest(clip_bitrate=6_000_000).estimate(60)["source"])

    def test_full_seconds_says_what_the_choice_buys(self):
        # 45 MB at 7.5 Mbit/s runs out around 49 s - which is the useful
        # thing to say, because a 45-second clip is exactly what someone
        # picking it may have in mind.
        self.assertEqual(dest(clip_bitrate=7_500_000).estimate(60)["full_seconds"],
                         49)

    def test_a_lower_bitrate_lasts_longer(self):
        self.assertGreater(
            dest(clip_bitrate=3_750_000).estimate(60)["full_seconds"],
            dest(clip_bitrate=7_500_000).estimate(60)["full_seconds"])

    def test_the_default_covers_a_minute(self):
        self.assertGreaterEqual(dest().estimate(60)["full_seconds"], 60)

    def test_full_seconds_does_not_depend_on_the_example_length(self):
        d = dest(clip_bitrate=10_000_000)
        self.assertEqual(d.estimate(10)["full_seconds"],
                         d.estimate(600)["full_seconds"])

    def test_no_duration_no_estimate(self):
        self.assertEqual(dest().estimate(0), {})

    def test_discord_clamps_much_harder(self):
        d = destinations.build(dict(DC, clip_bitrate=6_000_000))
        self.assertLess(d.estimate(60)["bitrate"], 2_000_000)


class TestALighterRecordingIsLeftAlone(unittest.TestCase):
    """The bitrate is a ceiling, and nothing is ever encoded up to it.

    Which is what makes lowering Steam's own recording quality simply
    leave more room, rather than something the plugin fights. Measured
    on a Deck with a 6.6 Mbit/s recording: picked at 12.8 and at 6 it
    went out untouched, and only 3 caused a re-encode.
    """

    def setUp(self):
        self.real_probe = media.probe
        self.real_fps = media.source_fps
        self.real_encode = media._encode
        self.encoded = False

        def fake_encode(src, dst, bitrate, fps, maxh, progress=None):
            self.encoded = True
            with open(dst, "wb") as fh:
                fh.write(b"x" * 1024)
            return True

        media.source_fps = lambda p: 30.0
        media._encode = fake_encode

    def tearDown(self):
        media.probe = self.real_probe
        media.source_fps = self.real_fps
        media._encode = self.real_encode

    def run_with(self, megabytes, seconds, bitrate, maxh=0):
        media.probe = lambda p: (1280, 800, seconds)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
            fh.write(b"y" * int(megabytes * 1024 * 1024))
            src = fh.name
        try:
            out, tmp = media.prepare_video(
                src, tg.BOT_LIMIT, tg.SIZE_TARGET, bitrate, 30, maxh,
                floor=media.FLOOR)
            if tmp:
                os.unlink(tmp)
            return out == src
        finally:
            os.unlink(src)

    def test_a_light_recording_is_sent_as_it_is(self):
        # ~0.8 Mbit/s against a 12.8 ceiling.
        self.assertTrue(self.run_with(1, 10, 12_800_000))
        self.assertFalse(self.encoded)

    def test_the_same_holds_at_a_lower_ceiling(self):
        self.assertTrue(self.run_with(1, 10, 6_000_000))
        self.assertFalse(self.encoded)

    def test_a_heavy_recording_is_brought_down(self):
        # ~33 Mbit/s: past the ceiling and past the limit.
        self.assertFalse(self.run_with(40, 10, 12_800_000))
        self.assertTrue(self.encoded)

    def test_a_taller_frame_is_encoded_even_when_it_would_fit(self):
        # Passing a light clip straight through skipped the scale too,
        # so asking for 480p did nothing whenever the clip happened to
        # fit - which, on "as recorded", is most of them.
        self.assertFalse(self.run_with(1, 10, media.SOURCE, maxh=480))
        self.assertTrue(self.encoded)

    def test_a_frame_already_within_the_cap_still_passes_through(self):
        self.assertTrue(self.run_with(1, 10, media.SOURCE, maxh=800))
        self.assertFalse(self.encoded)

    def test_no_cap_means_no_reason_to_encode(self):
        self.assertTrue(self.run_with(1, 10, media.SOURCE, maxh=0))
        self.assertFalse(self.encoded)

    def test_a_faster_recording_is_encoded_even_when_it_would_fit(self):
        # The fps filter lives in the encode, so passing a light clip
        # straight through left it at the rate it was recorded at, and
        # picking 30 did nothing to a 60 fps clip (reported 2026-09-16:
        # "30fps option doesn't work, it stays in 60fps all the time").
        media.source_fps = lambda p: 60.0
        self.assertFalse(self.run_with(1, 10, media.SOURCE))
        self.assertTrue(self.encoded)

    def test_a_recording_already_at_the_asked_rate_passes_through(self):
        media.source_fps = lambda p: 30.0
        self.assertTrue(self.run_with(1, 10, media.SOURCE))
        self.assertFalse(self.encoded)

    def test_a_slower_recording_is_not_encoded_to_speed_it_up(self):
        media.source_fps = lambda p: 24.0
        self.assertTrue(self.run_with(1, 10, media.SOURCE))
        self.assertFalse(self.encoded)


class TestScalingSurvivesAnUnhelpfulEncode(unittest.TestCase):
    """A smaller frame must still be delivered smaller.

    Measured on a Deck: a 14 s 23.9 MB clip at "as recorded" + 480p came
    back 1280x800.  The scale did run, but the encode was aimed at the
    26 Mbit/s the size limit allowed rather than the 14 Mbit/s the clip
    actually had, so the output grew and the "compression did not help"
    fallback handed the original back - 480p once again doing nothing.
    """

    def setUp(self):
        self.real_probe = media.probe
        self.real_fps = media.source_fps
        self.real_encode = media._encode
        self.asked = {}

        def fake_encode(src, dst, bitrate, fps, maxh, progress=None):
            # Writes what it was told to: the bug only shows when the
            # encoder is taken at its word.
            self.asked["bitrate"] = bitrate
            with open(dst, "wb") as fh:
                fh.write(b"x" * (bitrate * 14 // 8))
            return True

        media.probe = lambda p: (1280, 800, 14)
        media.source_fps = lambda p: 30.0
        media._encode = fake_encode

    def tearDown(self):
        media.probe = self.real_probe
        media.source_fps = self.real_fps
        media._encode = self.real_encode

    def prepare(self, maxh):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
            fh.write(b"y" * (14_000_000 * 14 // 8))     # 14 Mbit/s, 14 s
            src = fh.name
        try:
            out, tmp = media.prepare_video(
                src, tg.BOT_LIMIT, tg.SIZE_TARGET, media.SOURCE, 30, maxh,
                floor=media.FLOOR)
            if tmp:
                os.unlink(tmp)
            return out == src
        finally:
            os.unlink(src)

    def test_the_shrunken_frame_is_the_one_sent(self):
        self.assertFalse(self.prepare(480))

    def test_the_encode_is_never_aimed_above_the_source(self):
        self.prepare(480)
        self.assertLessEqual(self.asked["bitrate"], 14_000_000)

    def test_a_frame_within_the_cap_is_still_left_alone(self):
        self.assertTrue(self.prepare(800))

    def test_a_recording_lighter_than_the_floor_is_not_refused(self):
        # A 6 s 0.25 MB clip is ~350 kbit/s, under the 400 kbit/s floor
        # on its own.  Capping the target at the source rate must not
        # turn that into "too long to fit at watchable quality" - the
        # floor guards the size budget, and this clip needs none of it.
        media.probe = lambda p: (1280, 800, 6)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
            fh.write(b"y" * 262_144)
            src = fh.name
        try:
            out, tmp = media.prepare_video(
                src, tg.BOT_LIMIT, tg.SIZE_TARGET, media.SOURCE, 30, 480,
                floor=media.FLOOR)
            if tmp:
                os.unlink(tmp)
            self.assertNotEqual(out, src)
        finally:
            os.unlink(src)


class TestNeverInventFrames(unittest.TestCase):
    """Asking 60 fps of a 30 fps recording must not duplicate frames.

    Measured on a Deck before this was handled: 44.8 MB against 25.2 MB
    for a file that looked exactly the same.
    """

    def setUp(self):
        self.real_probe = media.probe
        self.real_fps = media.source_fps
        self.real_encode = media._encode
        self.seen = {}

        def fake_encode(src, dst, bitrate, fps, maxh, progress=None):
            self.seen["bitrate"] = bitrate
            self.seen["fps"] = fps
            with open(dst, "wb") as fh:
                fh.write(b"x" * 1024)
            return True

        media.probe = lambda p: (1280, 800, 60)
        media._encode = fake_encode

    def tearDown(self):
        media.probe = self.real_probe
        media.source_fps = self.real_fps
        media._encode = self.real_encode

    def prepare(self, source_rate, asked_fps, bitrate, floor):
        media.source_fps = lambda p: source_rate
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
            fh.write(b"y" * (80 * 1024 * 1024))     # far over any limit
            src = fh.name
        try:
            _, tmp = media.prepare_video(
                src, tg.BOT_LIMIT, tg.SIZE_TARGET, bitrate, asked_fps,
                0, floor=floor)
            if tmp:
                os.unlink(tmp)
        finally:
            os.unlink(src)

    def test_a_thirty_fps_source_is_encoded_at_thirty(self):
        self.prepare(30.0, 60, 6_000_000, 800_000)
        self.assertEqual(self.seen["fps"], 30)

    def test_the_extra_budget_goes_back_with_the_frames(self):
        self.prepare(30.0, 60, 6_000_000, 800_000)
        self.assertEqual(self.seen["bitrate"], 3_000_000)

    def test_a_sixty_fps_source_keeps_sixty(self):
        self.prepare(60.0, 60, 6_000_000, 800_000)
        self.assertEqual(self.seen["fps"], 60)
        self.assertEqual(self.seen["bitrate"], 6_000_000)

    def test_broadcast_rates_are_not_treated_as_lower(self):
        # 59.94 fps is 60 for our purposes; rounding it down would hand
        # back budget for nothing.
        self.prepare(60_000 / 1001, 60, 6_000_000, 800_000)
        self.assertEqual(self.seen["fps"], 60)

    def test_an_unknown_source_rate_changes_nothing(self):
        self.prepare(0.0, 60, 6_000_000, 800_000)
        self.assertEqual(self.seen["fps"], 60)
        self.assertEqual(self.seen["bitrate"], 6_000_000)

    def test_asking_for_less_than_the_source_still_caps(self):
        self.prepare(60.0, 30, 3_000_000, 400_000)
        self.assertEqual(self.seen["fps"], 30)
        self.assertEqual(self.seen["bitrate"], 3_000_000)


class TestWhatWeEncodeWith(unittest.TestCase):
    """H.264 goes out, the GPU encodes it, the software scaler scales it.

    Measured on a Deck at 2.5 Mbit/s: hevc_vaapi scored below
    h264_vaapi, and scale_vaapi below the software scaler, so both are
    out.  Of the two H.264 encoders the hardware one goes first - on an
    APU a CPU encode during play costs the game frames - and x264 is the
    fallback, held to two threads for the same reason.
    """

    def setUp(self):
        self.real_probe = media.probe
        self.real_run = media._run_ffmpeg
        self.cmds = []

        def fake_run(cmd, dur, progress=None):
            self.cmds.append(cmd)
            return False        # keep going so every attempt is seen

        media.probe = lambda p: (1280, 800, 10)
        media._run_ffmpeg = fake_run

    def tearDown(self):
        media.probe = self.real_probe
        media._run_ffmpeg = self.real_run

    def encode(self, maxh=480):
        media._encode("in.mp4", "out.mp4", 2_500_000, 30, maxh)
        return [" ".join(c) for c in self.cmds]

    def test_nothing_reaches_for_hevc(self):
        self.assertFalse([c for c in self.encode() if "hevc" in c])

    def test_the_first_attempt_is_the_gpu_h264_encoder(self):
        self.assertIn("h264_vaapi", self.encode()[0])

    def test_software_h264_is_kept_as_a_fallback(self):
        self.assertIn("libx264", self.encode()[1])

    def test_the_software_fallback_is_held_to_two_threads(self):
        for cmd in self.encode():
            if "libx264" in cmd:
                self.assertIn("-threads 2", cmd)
            else:
                self.assertNotIn("-threads", cmd)

    def test_scaling_never_goes_through_the_gpu_scaler(self):
        self.assertFalse([c for c in self.encode() if "scale_vaapi" in c])

    def test_every_attempt_scales_and_sets_the_rate(self):
        for cmd in self.encode():
            self.assertIn("scale=-2:480", cmd)
            self.assertIn("fps=30", cmd)

    def test_a_frame_within_the_cap_is_not_scaled(self):
        for cmd in self.encode(maxh=800):
            self.assertNotIn("scale=", cmd)


if __name__ == "__main__":
    unittest.main()
