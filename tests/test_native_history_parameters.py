"""Undoing a curve changes content even when clip geometry stays identical."""
import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from live_editor import operations

class ParameterHistory(unittest.TestCase):
    def test_history_observes_parameter_change_with_same_geometry(self):
        before={'tracks':[{'type':'video','segments':[{'id':'v','target_timerange':{'duration':4000000}}]}],
                'materials':{'speeds':[{'curve_speed':{'speed_points':[{'x':0,'y':1},{'x':1,'y':2}]}}]},'duration':4000000}
        after={**before,'materials':{'speeds':[{'curve_speed':{'speed_points':[{'x':0,'y':1.2},{'x':1,'y':1.8}]}}]}}
        editor=Mock();editor.confirm_saved.return_value={'snapshot':{'token':'same','revision':['same-geometry']}}
        editor.saved.side_effect=[{'timeline':before},{'timeline':after}]
        with patch.object(operations.time,'sleep'):
            result=operations.confirm_parameter_history(editor,'same',before,timeout=2)
        self.assertEqual(result['snapshot']['revision'],['same-geometry'])
        self.assertEqual(editor.confirm_saved.call_count,2)
        for call in editor.confirm_saved.call_args_list:self.assertNotIn('changed_revision',call.kwargs)

if __name__=='__main__':unittest.main()
