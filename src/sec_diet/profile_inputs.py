"""Build local profile instances only from eligible POF meals of that profile."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

from .cohort import FIXED_TAP_WATER_KEY, residents_from_zip
from .instances import environmental_coefficients, write_json
from .layout import NUTRIENT_FIELDS, NUTRIENT_START, NUTRIENT_WIDTH, code, field, VALID_DAYS
from .profile_model import ProfileModel
from .profiles import profile_lookup
from .source_checks import FOOTPRINT_SHEET, consumption_lines, input_info


def food_groups(workbook: Path) -> dict:
    book = load_workbook(workbook, read_only=True, data_only=True)
    result, group = {}, None
    try:
        for row in book[FOOTPRINT_SHEET].iter_rows(min_row=4, values_only=True):
            if row[0] is None and isinstance(row[1], str) and all(v is None for v in row[2:7]):
                group = row[1].strip()
            if isinstance(row[0], (int, float)):
                if group is None:
                    raise ValueError("An environmental food has no documented group")
                result[(code(row[0]), code(row[2]))] = group
    finally:
        book.close()
    return result


def stable_id(identity: tuple) -> str:
    return hashlib.sha256("|".join(identity).encode()).hexdigest()[:24]


MEAL_SLOTS = ("breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner", "supper")


def meal_slot(occasion: str, hour_text: str) -> int:
    """POF occasion first; recorded hour splits snacks and classifies other occasions."""
    explicit = {"1": 0, "2": 2, "4": 4, "5": 5}
    if occasion in explicit:
        return explicit[occasion]
    if occasion not in {"3", "6", "9"}:
        raise ValueError("Unknown POF eating occasion")
    try:
        hour = int(hour_text.strip().upper().removesuffix("H"))
    except ValueError as exc:
        raise ValueError("A snack/other occasion requires a valid recorded hour") from exc
    if not 0 <= hour <= 23:
        raise ValueError("Recorded hour is outside 0--23")
    if occasion == "3":
        return 1 if hour < 12 else 3
    if 4 <= hour < 9: return 0
    if 9 <= hour < 11: return 1
    if 11 <= hour < 14: return 2
    if 14 <= hour < 17: return 3
    if 17 <= hour < 21: return 4
    return 5


def assemble_profile(profile, selected, groups, environmental):
    """Retain all recorded portions, nutrient amounts and six absent/present slots."""
    variables = sorted({key for _,state in selected for key in state["items"] if key[:2] != FIXED_TAP_WATER_KEY},
                       key=lambda key:(key[2],key[0],key[1] or ""))
    positions = {key:i for i,key in enumerate(variables)}
    pools = [[] for _ in MEAL_SLOTS]
    indices = [{} for _ in MEAL_SLOTS]
    observed = []
    baseline = np.zeros(len(variables))
    blank_counts = np.zeros(6,dtype=int)
    for identity,state in selected:
        vector=[]
        for slot in range(6):
            items=[];nutrients=np.zeros(len(NUTRIENT_FIELDS));carbon=water=0.
            for (food,prep,position),(grams,amounts) in sorted(state["items"].items(),key=lambda item:repr(item[0])):
                if position != slot: continue
                tap=(food,prep)==FIXED_TAP_WATER_KEY
                env=(0.,0.) if tap else environmental[(food,prep or "99")]
                group="Tap water" if tap else groups[(food,prep or "99")]
                items.append(dict(food_code=food,preparation_code=prep,grams=float(grams),food_group=group,tap_water=tap))
                nutrients+=amounts;carbon+=grams*env[0];water+=grams*env[1]
                if not tap: baseline[positions[(food,prep,slot)]]+=grams
            signature=repr(([(i['food_code'],i['preparation_code'],i['grams']) for i in items],nutrients.tolist()))
            if signature not in indices[slot]:
                indices[slot][signature]=len(pools[slot])
                pools[slot].append(dict(meal_id=hashlib.sha256(signature.encode()).hexdigest()[:24],slot=MEAL_SLOTS[slot],
                    items=items,nutrients=nutrients.tolist(),carbon_gco2e=float(carbon),water_l=float(water),source_day_ids=[]))
            entry_index=indices[slot][signature]
            pools[slot][entry_index]["source_day_ids"].append(hashlib.sha256(repr(identity).encode()).hexdigest()[:24])
            vector.append(entry_index);blank_counts[slot]+=int(not items)
        observed.append(vector)
    if not observed: raise ValueError("No eligible source days for profile " + profile['profile_id'])
    baseline/=len(observed)
    return dict(schema_version="3.0",profile=profile,variables=[dict(food_code=f,preparation_code=p,occasion_code=str(m),
                    food_group=groups[(f,p or "99")]) for f,p,m in variables],
                baseline_g=baseline.tolist(),meal_slots=list(MEAL_SLOTS),meal_pools=pools,
                observed_diets=np.asarray(observed,dtype=int).tolist(),
                source_summary=dict(selected_distinct_respondents=len(observed),
                    pool_sizes=[len(pool) for pool in pools],observed_blank_slot_counts=blank_counts.tolist()))


def build_profiles(pof: Path, footprints: Path, catalogue: dict, design: dict, destination: Path) -> dict:
    sources={"pof":input_info(pof),"footprints":input_info(footprints)}
    for name,info in sources.items():
        if info['sha256']!=design['source_sha256'][name]:raise ValueError("Input checksum differs: "+name)
    lookup=profile_lookup(catalogue);residents,_=residents_from_zip(pof)
    assignments={k:lookup[v] for k,v in residents.items() if v in lookup}
    environmental,additions=environmental_coefficients(footprints);groups=food_groups(footprints)
    days={};failures=defaultdict(int);mapping_counts=defaultdict(int)
    with consumption_lines(pof) as lines:
        for raw in lines:
            record=raw.rstrip(b"\r\n").decode('latin-1')
            identity=tuple(field(record,n) for n in ('UF','COD_UPA','NUM_DOM','NUM_UC','COD_INFORMANTE'))
            profile_id=assignments.get(identity)
            if profile_id is None:continue
            day=field(record,'QUADRO')
            if day not in VALID_DAYS:raise ValueError('Unexpected source day')
            state=days.setdefault((identity,day),dict(profile_id=profile_id,valid=True,items={}))
            food,prep=code(field(record,'V9001')),code(field(record,'COD_PREPARACAO_FINAL'))
            try:
                slot=meal_slot(field(record,'V9017'),field(record,'V9015'))
                grams=float(field(record,'QTD'))
                amounts=np.asarray([float(record[NUTRIENT_START+i*NUTRIENT_WIDTH:NUTRIENT_START+(i+1)*NUTRIENT_WIDTH]) for i in range(len(NUTRIENT_FIELDS))])
                if not np.isfinite(grams) or grams<=0 or not np.isfinite(amounts).all() or (amounts<0).any():raise ValueError('Invalid composition or quantity')
                env_key=(food,prep or '99')
                if (food,prep)!=FIXED_TAP_WATER_KEY:
                    if env_key not in environmental or env_key not in groups or min(environmental[env_key])<=0 or (prep is None and food not in additions):raise ValueError('Missing positive environmental linkage')
            except ValueError as exc:
                state['valid']=False;failures[str(exc)]+=1;continue
            mapping_counts[field(record,'V9017')+'->'+MEAL_SLOTS[slot]]+=1
            entry=state['items'].setdefault((food,prep,slot),[0.,np.zeros(len(NUTRIENT_FIELDS))])
            entry[0]+=grams;entry[1]+=amounts
    destination.mkdir(parents=True,exist_ok=True);descriptions=[]
    for profile in catalogue['profiles']:
        eligible=[(key,s) for key,s in days.items() if s['profile_id']==profile['profile_id'] and s['valid']
                  and s['items'] and sum(v[1][0] for v in s['items'].values())>0
                  and any(k[:2]!=FIXED_TAP_WATER_KEY for k in s['items'])]
        by_person=defaultdict(list)
        for key,state in eligible:by_person[key[0]].append((key,state))
        selected=[min(rows,key=lambda row:stable_id(row[0][0]+(row[0][1],))) for rows in by_person.values()]
        selected.sort(key=lambda row:stable_id(row[0][0]))
        instance=assemble_profile(profile,selected,groups,environmental)
        instance['study_id']=design['study_id'];model=ProfileModel(instance,design)
        file=destination/(profile['profile_id']+'.json');write_json(file,instance)
        descriptions.append(dict(profile_id=profile['profile_id'],eligible_days=len(eligible),
            **instance['source_summary'],distinct_observed_vectors=len(model.sampling_pool),
            observed_numerically_feasible=sum(model.evaluate(x)['feasible'] for x in model.initial_pool),
            instance=dict(filename=file.name,sha256=input_info(file)['sha256'])))
    manifest=dict(study_id=design['study_id'],sources=sources,profiles=descriptions,
        mapping_counts=dict(mapping_counts),invalid_line_reasons=dict(failures),
        reconstruction='Whole observed slot intakes: sums of reported absolute nutrient quantities, without nutrient regression or portion scaling.',
        privacy='Individual meals and composition amounts remain in ignored local results.')
    write_json(destination/'manifest.json',manifest);return manifest
