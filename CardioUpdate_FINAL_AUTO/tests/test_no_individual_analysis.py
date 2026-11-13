"""Keep paid model calls confined to the daily briefing."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NoIndividualAnalysisTests(unittest.TestCase):
    def test_only_the_briefing_imports_openai(self):
        callers = []
        for path in (ROOT / 'scripts').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('openai'):
                    callers.append(path.name)
                if isinstance(node, ast.Import) and any(alias.name.startswith('openai') for alias in node.names):
                    callers.append(path.name)
        self.assertEqual(callers, ['update_briefing.py'])
        self.assertFalse((ROOT / 'scripts' / 'ai_analysis.py').exists())

    def test_only_daily_briefing_receives_the_openai_key(self):
        workflow = (ROOT.parent / '.github' / 'workflows' / 'daily-update.yml').read_text(encoding='utf-8')
        sections = re.split(r'      - name: ', workflow)
        uses = [section.strip().splitlines()[0] for section in sections if 'OPENAI_API_KEY' in section]
        self.assertEqual(uses, ['Generate daily briefing'])

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for view regression')
    def test_legacy_analysis_is_not_read_or_displayed(self):
        javascript = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[1],'utf8');
for(const [,script] of html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(script);
const start=html.indexOf('function openStudy(id){'),end=html.indexOf('\nfunction runSearch',start);
assert(start>=0 && end>start);
const source={id:'source',title:'Original title',area:'Cardiología',level:'Relevante',type:'Ensayo',journal:'Revista',date:'2026-11-13',url:'https://doi.org/verified',abstract_en:'Original abstract'};
Object.defineProperty(source,'analysis_es',{get(){throw Error('Retired analysis must not be read');}});
const box={innerHTML:''};
vm.runInNewContext(html.slice(start,end)+"\nopenStudy('source');",{
STUDIES:[source],previous:'week',document:{querySelector:()=>({id:'week'}),getElementById:()=>box},
areaOf:()=>['Cardiología','#123','','Cardiología'],esc:x=>String(x||''),originalAbstractFor:s=>s.abstract_en,isFav:()=>false,go:()=>{}
});
assert(box.innerHTML.includes('Original title'));
assert(box.innerHTML.includes('Original abstract'));
assert(box.innerHTML.includes('https://doi.org/verified'));
assert(!box.innerHTML.includes('Análisis CardioUpdate'));
'''
        result = subprocess.run(['node','-e',javascript,str(ROOT/'index.html')],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
