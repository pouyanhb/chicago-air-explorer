import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_data as b


class BuildDataTests(unittest.TestCase):
    def sample(self, day, sensor, pm, no, name=None):
        return {'startofperiod':day+'T00:00:00.000', 'datasourceid':sensor,
                'sensor_name':name or sensor,'latitude':41.88,'longitude':-87.65,
                'pm2_5concmass24hourmean_value':str(pm) if pm is not None else None,
                'no2conc24hourmean_value':str(no) if no is not None else None}

    def test_daily_network_equal_sensor_weights(self):
        records,meta={},{}
        b.process_daily([self.sample('2026-10-01','A',10,4),self.sample('2026-10-01','B',20,None),
                         self.sample('2026-10-02','A',8,5),self.sample('2026-10-02','B',None,7)],records,meta)
        result=b.assemble_daily(records,meta,'2026-10-03T00:00:00Z')
        self.assertEqual(result['network'][0],[0,15.0,4.0,2,1])
        self.assertEqual(result['network'][1],[1,8.0,6.0,1,2])
        self.assertEqual(len(result['rows']),4)
        self.assertEqual(result['day_timezone'],'UTC')

    def test_revisions_are_updated_not_appended(self):
        records,meta={},{}
        b.process_daily([self.sample('2026-10-01','A',10,4)],records,meta)
        b.process_daily([self.sample('2026-10-01','A',12,5)],records,meta)
        self.assertEqual(len(records),1)
        self.assertEqual(records[('2026-10-01','A')],(12.0,5.0))

    def test_bad_measurements_become_missing_not_zero(self):
        records,meta={},{}
        b.process_daily([self.sample('2026-10-01','A',-5,None)],records,meta)
        self.assertEqual(records[('2026-10-01','A')],(None,None))

    def test_duplicate_sensor_day_is_rejected(self):
        row=self.sample('2026-10-01','A',10,4)
        with self.assertRaises(RuntimeError): b.process_daily([row,row],{}, {})

    def test_roundtrip_cache(self):
        records,meta={},{}
        b.process_daily([self.sample('2026-10-01','A',10,4)],records,meta)
        assembled=b.assemble_daily(records,meta,'2026-10-03T00:00:00Z')
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'daily.json';b.write_json(p,assembled)
            records2,meta2,last=b.load_daily_cache(p)
        self.assertEqual(records,records2)
        self.assertEqual(last,'2026-10-01')
        self.assertEqual(meta2['A']['name'],'A')

    def test_hourly_same_hour_map(self):
        class MockResult:
            def raise_for_status(self): pass
            def json(self): return [{'startofperiod':'2026-10-03T22:00:00.000'}]
        class MockSession:
            def get(self,*args,**kwargs): return MockResult()
        rows=[]
        for i in range(20):
            rows.append({'startofperiod':'2026-10-03T22:00:00.000','datasourceid':str(i),
                         'pm2_5concmass1hourmean_value':'5','no2conc1hourmean_value':'7'})
        with patch.object(b,'fetch_pages',return_value=rows):
            obj=b.build_recent(MockSession(),set(map(str,range(20))),'now')
        self.assertEqual(obj['map_hour'],'2026-10-03T22:00:00')
        self.assertEqual(len(obj['map_rows']),20)
        self.assertEqual(obj['network'][0][3:], [20,20])

if __name__=='__main__': unittest.main()
