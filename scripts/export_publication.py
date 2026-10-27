"""Regenerate publication displays from an already completed campaign."""
from pathlib import Path
import argparse
import json
from sec_diet.publication_outputs import export_publication

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    print(json.dumps(export_publication(args.campaign,args.output),indent=2))
