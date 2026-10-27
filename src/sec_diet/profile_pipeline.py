"""One entry point from independent input files to all revised article outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import importlib.metadata
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .instances import read_json, write_json
from .profile_targets import maintenance_energy, targets
from .source_checks import input_info

REPOSITORY = Path(__file__).resolve().parents[2]


def is_nonnegative(value):
    return math.isfinite(value) and value >= 0


def configuration(catalogue, evaluations, replicates, penalty=False, penalty_weight=0.):
    old = read_json(REPOSITORY/"docs/protocol/design.json")
    implementation = old["implementation"].copy()
    implementation["initial_population"] = "66 distinct observed diets from the same profile; matched across algorithms"
    implementation["quantity_repair"] = "integer meal indices within position-specific pools; preserve all recorded food portions"
    implementation["crossover"] = dict(name="uniform whole-meal exchange", probability=.9)
    implementation["mutation"] = dict(name="categorical whole-meal replacement", probability=1., probability_per_slot="1/6")
    implementation['openpyxl_version']='3.1.5'
    implementation['matplotlib_version']='3.11.2'
    implementation['spea2_constant_coordinate_guard']='unit divisor for zero-span coordinates; finite internal fitness required'
    return dict(schema_version="4.1", study_id="sec2026-pof-meals-v4.1-"+(f"penalty-{penalty_weight:g}" if penalty else "no-penalty"),
        seed_namespace="sec2026-pof-meals-v4-main",
        nutrition_objective="capped_attainment_percent", penalty_enabled=bool(penalty),
        penalty_weight=float(penalty_weight) if penalty else 0.,
        penalty_rule="add weight times mean relative lower-target shortfall to C, W and D after fixed normalization; retain N as 1-mean capped attainment",
        profiles=[p["profile_id"] for p in catalogue["profiles"]],
        profile_definitions=catalogue["profiles"], objective_subsets=catalogue["objective_pairs"]+catalogue["objective_triples"],
        algorithms=old["algorithms"], source_sha256=old["source_sha256"], implementation=implementation,
        evaluations=evaluations, replicates=replicates, wall_time_limit_seconds=3600,
        energy_tolerance_fraction=.05, target_attainment_relative_tolerance=1e-6,
        analysis=dict(permutation_draws=99999, bootstrap_draws=9999, holm_family="144 profile contrasts and 36 equal-profile global contrasts"),
        nutrient_scope="23 sourced nutrient criteria; energy is a hard constraint; all 29 POF fields remain available for description",
        excluded_targets=dict(FOLATO="No verified DFE correspondence in the source dictionary",

                              AGMONO="No single total-monounsaturated-fat DRI target",
                              AGPOLI="Total polyunsaturated fat is not separate n-3 and n-6 intake",
                              COLEST="No numeric DRI upper threshold", ENERGIA_KJ="Duplicate energy representation"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pof", type=Path, required=True, help="Independently obtained POF ZIP")
    parser.add_argument("--footprints", type=Path, required=True, help="Independently obtained footprint workbook")
    parser.add_argument("--output-dir", type=Path, help="New campaign directory; defaults include formulation and penalty mode")
    parser.add_argument("--catalogue", type=Path, default=REPOSITORY/"docs/profiles/catalogue.json")
    parser.add_argument("--evaluations", type=int, default=16500)
    parser.add_argument("--replicates", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    penalty_mode=parser.add_mutually_exclusive_group()
    penalty_mode.add_argument("--penalty",action="store_true",help="Apply calibrated shortage penalties to non-nutritional objectives")
    penalty_mode.add_argument("--no-penalty",action="store_true",help="Use capped attainment without extra shortage penalties")
    parser.add_argument("--penalty-weight",type=float,help="Explicit nonnegative penalty weight; otherwise use docs/profiles/penalty-selection.json")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true", help="Prepare local profile inputs and matrix without optimizer runs")
    mode.add_argument("--analyze-only", action="store_true", help="Check all saved runs and regenerate article outputs")
    parser.add_argument("--resume", action="store_true", help="Recheck and retain completed runs; partial runs require diagnosis")
    args=parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("Worker count must be between one and eight")
    if args.replicates < 2 or args.evaluations < 66 or args.evaluations % 66:
        parser.error("At least two replicates and an evaluation count divisible by population 66 are required")
    for path in (args.pof,args.footprints,args.catalogue):
        if not path.is_file(): parser.error(f"Missing input: {path}")
    for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[name]="1"
    # Imports follow the thread settings, including in spawned Windows workers.
    from .profile_inputs import build_profiles
    from .profile_runner import run_plan, execute_task, validate_run
    from .runner import code_revision, validate_environment, versions
    from .profile_results import summarize, save_csv
    from .profile_model import ProfileModel
    from .profile_diagnostics import feasibility_relaxation
    from .profile_methods import export_methods, export_preparation
    catalogue=read_json(args.catalogue)
    for profile in catalogue["profiles"]:
        if profile["height_m"] is None or profile["weight_kg"] is None:
            parser.error("Profile anthropometry is not defined")
        if abs(profile["weight_kg"]/profile["height_m"]**2 - profile["bmi_kg_m2"]) > .01:
            parser.error("Profile weight, height and BMI are inconsistent")
        if abs(profile["maintenance_kcal"]-maintenance_energy(profile)) > 1e-8:
            parser.error("Stored maintenance energy differs from the cited equation")
    target_table=read_json(args.catalogue.parent/catalogue['nutrient_targets'])
    if target_table['profiles']!={p['profile_id']:targets(p) for p in catalogue['profiles']}:
        raise ValueError("The documented target table differs from the implemented target rules")
    weight=0.
    penalty_evidence=None
    if args.penalty:
        if args.penalty_weight is None:
            selection_path=REPOSITORY/'docs/profiles/penalty-selection.json'
            if not selection_path.is_file():parser.error("Run scripts/study_penalty_weights.py before the calibrated --penalty campaign, or supply --penalty-weight")
            calibration=read_json(selection_path)
            if calibration['protocol'].get('spea2_constant_coordinate_guard') is not True:
                parser.error('Repeat scripts/study_penalty_weights.py with the v4.1 SPEA2 normalization guard before using the calibrated penalty')
            weight=float(calibration['selected_weight'])
            penalty_evidence=input_info(selection_path)
        else:weight=args.penalty_weight
        if not is_nonnegative(weight):parser.error("Penalty weight must be finite and nonnegative")
    elif args.penalty_weight is not None:parser.error("--penalty-weight requires --penalty")
    design=configuration(catalogue,args.evaluations,args.replicates,args.penalty,weight)
    if penalty_evidence is not None:design['penalty_calibration']=penalty_evidence
    validate_environment(design)
    for package in ('openpyxl','matplotlib'):
        if importlib.metadata.version(package)!=design['implementation'][package+'_version']:
            raise ValueError(f"{package} differs from the registered version")
    signature=hashlib.sha256(json.dumps(dict(design=design,catalogue=catalogue),sort_keys=True).encode()).hexdigest()
    output=(args.output_dir or REPOSITORY/'results'/('meal-profile-study-v4.1-penalty-'+f'{weight:g}' if args.penalty else 'meal-profile-study-v4.1-no-penalty')).resolve()
    output.mkdir(parents=True,exist_ok=True)
    registered=output/"study.json"
    if registered.exists():
        if read_json(registered)["signature"] != signature:
            raise ValueError("Output directory belongs to another design. Select a new --output-dir.")
    else:
        if args.analyze_only: raise ValueError("No saved campaign in this directory")
        write_json(registered,dict(signature=signature,design=design,catalogue=catalogue))
    preparation_modules=('source_checks','cohort','instances','layout','profiles','profile_inputs','profile_targets','profile_model')
    preparation_hash=hashlib.sha256(''.join(input_info(Path(__file__).parent/(name+'.py'))['sha256'] for name in preparation_modules).encode()).hexdigest()
    instance_root=output/"inputs"/preparation_hash[:12]
    manifest_path=instance_root/"manifest.json"
    if manifest_path.exists():
        manifest=read_json(manifest_path)
        for name,path in (("pof",args.pof),("footprints",args.footprints)):
            if input_info(path)["sha256"] != manifest["sources"][name]["sha256"]:
                raise ValueError("Source input differs from prepared campaign")
        for profile in manifest["profiles"]:
            if input_info(instance_root/profile["instance"]["filename"])["sha256"] != profile["instance"]["sha256"]:
                raise ValueError("Prepared profile instance checksum differs")
    else:
        if args.analyze_only: raise ValueError("Prepared inputs are missing")
        manifest=build_profiles(args.pof,args.footprints,catalogue,design,instance_root)
    rows=run_plan(design)
    save_csv(output/"run-matrix.csv",rows)
    save_csv(output/"nutrient-targets.csv",[dict(profile_id=p["profile_id"],**row) for p in catalogue["profiles"] for row in targets(p)])
    write_json(output/"nutritional-feasibility-relaxation.json",dict(study_id=design['study_id'],
        profiles=[feasibility_relaxation(ProfileModel(read_json(instance_root/(p+'.json')),design)) for p in design['profiles']]))
    export_methods(catalogue,design,output/'preparation')
    export_preparation(manifest,output/'preparation')
    print(json.dumps(dict(study_id=design["study_id"],runs=len(rows),evaluations_per_run=args.evaluations,
        total_evaluations=len(rows)*args.evaluations, profiles=manifest["profiles"],output_dir=str(output)),indent=2),flush=True)
    if args.prepare_only:
        print("Profile inputs and matrix prepared. No optimizer run was started.")
        return 0
    environment=dict(versions(),openpyxl=importlib.metadata.version('openpyxl'),matplotlib=importlib.metadata.version('matplotlib'))
    provenance=dict(signature=signature,code_revision=code_revision(),environment=environment,
        instance_manifest_sha256=input_info(manifest_path)["sha256"], catalogue_sha256=input_info(args.catalogue)["sha256"])
    execution=output/"execution.json"
    if execution.exists():
        if read_json(execution) != provenance:
            raise ValueError("Code, environment or inputs differ from saved execution. Start a separate campaign.")
    else:
        if args.analyze_only: raise ValueError("Execution provenance is missing")
        write_json(execution,provenance)
    run_root=output/"runs"
    if args.analyze_only:
        for i,row in enumerate(rows,1):
            validate_run(run_root/row["run_id"],row,design,read_json(instance_root/(row["profile_id"]+'.json')),provenance)
            if i%20==0:print(f"Checked {i}/{len(rows)} runs",flush=True)
    else:
        states=[]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(execute_task,row,design,str(instance_root/(row["profile_id"]+'.json')),
                       str(run_root/row["run_id"]),provenance,args.resume):row for row in rows}
            with (output/"progress.jsonl").open('a',encoding='utf-8',newline='\n') as stream:
                for i,future in enumerate(as_completed(futures),1):
                    row=futures[future]
                    try: state=future.result()
                    except Exception as exc:state=dict(run_id=row['run_id'],state='failed',reason=str(exc))
                    states.append(state);stream.write(json.dumps(state,allow_nan=False)+'\n');stream.flush()
                    print(f"{i}/{len(rows)} {row['profile_id']} {row['objective_subset']} {row['algorithm']} {state['state']}",flush=True)
        failures=[s for s in states if s['state']=='failed']
        write_json(output/"completion.json",dict(planned_runs=len(rows),complete_runs=len(rows)-len(failures),failures=failures))
        if failures:
            print("Analysis was not generated because some planned runs are incomplete. See completion.json.")
            return 1
    summarize(run_root,instance_root,rows,design,output/"article")
    export_methods(catalogue,design,output/'article/methods')
    export_preparation(manifest,output/'article/methods')
    if penalty_evidence is not None:
        from .diet_figures import export_calibration
        export_calibration(selection_path,output/'article/figures',output/'article/tables/penalty-calibration.tex')
    from shutil import copyfile
    copyfile(output/'nutritional-feasibility-relaxation.json',output/'article/nutritional-feasibility-relaxation.json')
    copyfile(registered,output/'article/study.json')
    copyfile(execution,output/'article/reproduction.json')
    copyfile(REPOSITORY/'docs/profiles/references.json',output/'article/references.json')
    copyfile(REPOSITORY/'docs/literature/comparison.json',output/'article/literature-comparison-evidence.json')
    (output/'article/README.md').write_text(
        '# Results of the dietary-profile study\n\n'
        'This directory is generated only after every planned run has passed rescoring and completion checks. '
        'The study and reproduction JSON files identify the exact inputs, configuration, code and environment.\n\n'
        'CSV files contain run indicators, profile/global summaries, paired contrasts, nutrient deficits/excesses, '
        'target attainment, food-group changes, baseline nutrients, convergence and the selected candidate/run indices. '
        'GLOBAL denotes equal-profile aggregation, not a Brazilian population estimate.\n\n'
        'The figures show actual nondominated candidate points, median/IQR indicator summaries, convergence, '
        'nutrient target attainment and food-group mass-share changes. N is capped nutrient attainment (%), maximized; '
        'C is kg CO2e/day; W is litres/day; D is quantity departure in percent. Three-dimensional plots use '
        'these same raw units and have complementary projections. Figure-run selections document the median-HV rule.\n\n'
        'The tables directory provides LaTeX indicator tables. The methods directory contains the profile/target '
        'tables and the methodological workflow in SVG and PDF. Empty fronts are reported as such and have '
        'no invented representative diet. The linear diagnostic is a relaxation of the binary whole-meal selection.\n',encoding='utf-8')
    final_manifest=read_json(output/'article/analysis-manifest.json')
    final_manifest['files']={str(p.relative_to(output/'article')):input_info(p) for p in (output/'article').rglob('*')
                             if p.is_file() and p.name!='analysis-manifest.json'}
    write_json(output/'article/analysis-manifest.json',final_manifest)
    # This stage reads the saved fronts and meal pools; it never starts another
    # optimizer run. It writes an independently hashed, private interpretation
    # bundle, including every reconstructed Pareto menu.
    subprocess.run([sys.executable, str(REPOSITORY/'scripts/export_pareto_diets.py'),
                    '--campaign', str(output), '--footprints', str(args.footprints)], check=True)
    if design.get('nutrition_objective')=='capped_attainment_percent':
        from .publication_outputs import export_publication
        export_publication(output)
    print(f"All planned results generated in {output/'article'}",flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
