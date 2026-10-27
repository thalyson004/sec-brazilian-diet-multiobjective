"""Reproduce all final reference-comparison outputs from a completed campaign."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','pof','footprints','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    campaign,pof,footprints,output=(getattr(args,k).resolve() for k in ('campaign','pof','footprints','output'))
    if output.exists():parser.error('Use a new output directory; prior results are preserved')
    output.mkdir(parents=True)
    fronts=output/'fronts'/campaign.name
    comparison=output/'comparisons/observed-profile-energy-context'
    sensitivity=output/'comparisons/compromise-selection-v1'
    reference=output/'comparisons/reference-compromise-v1'
    commands=[
        ('export_public_fronts.py',['--campaign',campaign,'--output',fronts]),
        ('extract_observed_comparison.py',['--pof',pof,'--footprints',footprints,'--campaign',campaign,'--output',comparison]),
        ('analyze_compromise_selection.py',['--fronts',fronts,'--comparison',comparison,'--campaign',campaign,'--output',sensitivity]),
        ('select_reference_compromises.py',['--campaign',campaign,'--comparison',comparison,'--sensitivity',sensitivity,'--output',reference])]
    for script,parameters in commands:
        print('Generating:',script,flush=True)
        subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,parameters)],cwd=ROOT,check=True)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(method='Postprocessing only; no optimizer execution; all original runs retained',
        execution_sha256=digest(campaign/'execution.json'),script_sha256=digest(Path(__file__)),
        stages={str(p.relative_to(output)).replace('\\','/'):digest(p) for p in
                (fronts/'manifest.json',comparison/'manifest.json',sensitivity/'manifest.json',reference/'manifest.json')})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print('Current manuscript tables:',reference/'observed-comparison.tex',reference/'nutrition-selections.tex',flush=True)

if __name__=='__main__':main()
