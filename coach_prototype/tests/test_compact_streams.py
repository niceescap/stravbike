"""Synthetic regression fixture for the supplied Strava/FIT timestamp reference."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from services.compact_ingestion import process_activity_streams
from services.fit_compact import best_avg, regularize, segments
from services.strava_compact import streams_to_channels, time_report

PAUSE_GAPS = [3, 30, 33, 11, 58, 20, 43, 13, 30, 59, 106]
ACTIVE_RUNS = [318] + [4] * 8 + [3] * 2 + [1061]


def reference_streams():
    """1406 raw records; 11 one-second clock gaps; 11 real stop-clock pauses."""
    idx = []
    cursor = 0
    drift_by_run = [5] + [0] * 10 + [6]
    for run_index, (active_length, double_gaps) in enumerate(zip(ACTIVE_RUNS, drift_by_run)):
        positions = [0]
        elapsed = 0
        intervals = active_length - double_gaps - 1
        for interval in range(intervals):
            elapsed += 2 if interval < double_gaps else 1
            positions.append(elapsed)
        idx.extend(cursor + value for value in positions)
        cursor += positions[-1]
        if run_index < len(PAUSE_GAPS):
            cursor += PAUSE_GAPS[run_index]
    assert len(idx) == 1406
    return {
        'time': idx,
        'watts': [0 if i % 71 == 0 else 138.0 for i in range(len(idx))],
        'cadence': [90.0] * len(idx),
        'heartrate': [180.0] * len(idx),
        'velocity_smooth': [8.0] * len(idx),
        'altitude': [100.0] * len(idx),
    }


class FakeStravaClient:
    def __init__(self, streams):
        self.streams = streams
        self.calls = 0

    def get_activity_streams(self, strava_id, *, types, resolution):
        self.calls += 1
        assert resolution == 'high'
        return {key: SimpleNamespace(data=self.streams[key]) for key in types if key in self.streams}


class CompactTimebaseTests(unittest.TestCase):
    def test_reference_pause_accounting_and_segments(self):
        streams = reference_streams()
        report = time_report(streams)
        channels = streams_to_channels(streams)
        self.assertEqual(report['points'], 1406)
        self.assertEqual(report['elapsed_s'], 1812)
        self.assertEqual(report['actif_s'], 1417)
        self.assertEqual(report['pause_total_s'], 395)
        self.assertEqual(report['sauts_2s'], 11)
        self.assertEqual(report['pause_count'], 11)
        self.assertTrue(report['monotone'])
        self.assertEqual([end - start for start, end in segments(channels, min_len=60)], [318, 1061])
        self.assertEqual(channels['tt'][356], 751)

    def test_zero_watts_are_active_and_no_window_crosses_pause(self):
        channels = streams_to_channels(reference_streams())
        self.assertTrue(np.any(channels['p'] == 0))  # coasting remains real data
        tt = np.array([0, 1, 2, 3, 20, 21, 22, 23])
        values = np.array([1, 1, 1, 1000, 1000, 1, 1, 1], dtype=float)
        self.assertIsNone(best_avg(values, 5, tt))  # no 5s window bridges stopped time

    def test_two_second_clock_drift_is_filled_but_not_counted_as_pause(self):
        streams = {'time': [0, 1, 3, 4, 5], 'watts': [10, 20, 40, 50, 60]}
        channels = streams_to_channels(streams)
        self.assertEqual(channels['tt'].tolist(), [0, 1, 2, 3, 4, 5])
        self.assertEqual(len(channels['p']), 6)
        self.assertEqual(channels['p'][2], 20)
        self.assertEqual(time_report(streams)['pause_count'], 0)

    def test_pipeline_fetches_once_and_longest_crop_matches_reference(self):
        streams = reference_streams()
        activity = SimpleNamespace(source_id=456, occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            elapsed_time_s=1812, moving_time_s=1417, device_watts=True,
            streams_json=None, compact_json=None, best_json=None)
        athlete = SimpleNamespace(weight_kg=38.0, ftp_watts=150, max_heartrate=202)
        client = FakeStravaClient(streams)
        summary, _ = process_activity_streams(activity, athlete, client)
        self.assertEqual(client.calls, 1)
        self.assertIsNotNone(activity.best_json)
        self.assertEqual(activity.compact_json, summary)
        race_client = FakeStravaClient(streams)
        race_summary, _ = process_activity_streams(activity, athlete, race_client, segment='longest')
        self.assertEqual(race_client.calls, 1)
        self.assertEqual(race_summary['crop'], [751, 1061])
        self.assertEqual(activity.compact_json['t'], summary['t'])  # stored value remains full ride

    def test_estimated_power_never_populates_best_json(self):
        streams = reference_streams()
        activity = SimpleNamespace(source_id=789, occurred_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            elapsed_time_s=1812, moving_time_s=1417, device_watts=False,
            streams_json=None, compact_json=None, best_json=None)
        athlete = SimpleNamespace(weight_kg=38.0, ftp_watts=150, max_heartrate=202)
        client = FakeStravaClient(streams)
        summary, _ = process_activity_streams(activity, athlete, client)
        self.assertEqual(client.calls, 1)
        self.assertIsNotNone(summary)
        self.assertIsNone(activity.best_json)


if __name__ == '__main__':
    unittest.main()
