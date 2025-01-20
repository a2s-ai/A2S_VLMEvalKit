import copy as cp
import json
from collections import defaultdict
from urllib.request import urlopen

import gradio as gr
import numpy as np
import pandas as pd

from meta_data import DEFAULT_BENCH, META_FIELDS, URL


def listinstr(lst, s):
    assert isinstance(lst, list)
    for item in lst:
        if item in s:
            return True
    return False


def load_results():
    data = json.loads(urlopen(URL).read())
    return data


def nth_large(val, vals):
    return sum([1 for v in vals if v > val]) + 1


def format_timestamp(timestamp):
    date = timestamp[:-6]
    time = timestamp[-6:]
    date = date[:-4] + '.' + date[-4:-2] + '.' + date[-2:]
    time = time[:-4] + ':' + time[-4:-2] + ':' + time[-2:]
    return date + ' ' + time


def model_size_flag(sz, FIELDS):
    if pd.isna(sz) and 'Unknown' in FIELDS:
        return True
    if pd.isna(sz):
        return False
    if '<4B' in FIELDS and sz < 4:
        return True
    if '4B-10B' in FIELDS and sz >= 4 and sz < 10:
        return True
    if '10B-20B' in FIELDS and sz >= 10 and sz < 20:
        return True
    if '20B-40B' in FIELDS and sz >= 20 and sz < 40:
        return True
    if '>40B' in FIELDS and sz >= 40:
        return True
    return False


def model_type_flag(line, FIELDS):
    if 'OpenSource' in FIELDS and line['OpenSource'] == 'Yes':
        return True
    if 'API' in FIELDS and line['OpenSource'] == 'No' and line['Verified'] == 'Yes':
        return True
    if 'Proprietary' in FIELDS and line['OpenSource'] == 'No' and line['Verified'] == 'No':
        return True
    return False


def BUILD_L1_DF(results, fields):
    check_box = {}
    check_box['essential'] = ['Method', 'Param (B)', 'Language Model', 'Vision Model']
    # revise there to set default dataset
    check_box['required'] = ['Avg Score', 'Avg Rank'] + DEFAULT_BENCH
    check_box['avg'] = ['Avg Score', 'Avg Rank']
    check_box['all'] = check_box['avg'] + fields
    type_map = defaultdict(lambda: 'number')
    type_map['Method'] = 'html'
    type_map['Language Model'] = type_map['Vision Model'] = 'html'
    type_map['OpenSource'] = type_map['Verified'] = 'str'
    check_box['type_map'] = type_map

    df = generate_table(results, fields)
    return df, check_box


def BUILD_L2_DF(results, dataset):
    res = defaultdict(list)
    sub = [v for v in results.values() if dataset in v]
    assert len(sub)
    fields = list(sub[0][dataset].keys())

    non_overall_fields = [x for x in fields if 'Overall' not in x]
    overall_fields = [x for x in fields if 'Overall' in x]
    if dataset == 'MME':
        non_overall_fields = [x for x in non_overall_fields if not listinstr(['Perception', 'Cognition'], x)]
        overall_fields = overall_fields + ['Perception', 'Cognition']
    if dataset == 'OCRBench':
        non_overall_fields = [x for x in non_overall_fields if not listinstr(['Final Score'], x)]
        overall_fields = ['Final Score']

    for m in results:
        item = results[m]
        if dataset not in item:
            continue
        meta = item['META']
        for k in META_FIELDS:
            if k == 'Param (B)':
                param = meta['Parameters']
                res[k].append(float(param.replace('B', '')) if param != '' else None)
            elif k == 'Method':
                name, url = meta['Method']
                res[k].append(f'<a href="{url}">{name}</a>')
            else:
                res[k].append(meta[k])
        fields = [x for x in fields]

        for d in non_overall_fields:
            res[d].append(item[dataset][d])
        for d in overall_fields:
            res[d].append(item[dataset][d])

    df = pd.DataFrame(res)
    all_fields = overall_fields + non_overall_fields
    # Use the first 5 non-overall fields as required fields
    required_fields = overall_fields if len(overall_fields) else non_overall_fields[:5]

    if dataset == 'OCRBench':
        df = df.sort_values('Final Score')
    elif dataset == 'COCO_VAL':
        df = df.sort_values('CIDEr')
    else:
        df = df.sort_values('Overall')
    df = df.iloc[::-1]

    check_box = {}
    check_box['essential'] = ['Method', 'Param (B)', 'Language Model', 'Vision Model']
    check_box['required'] = required_fields
    check_box['all'] = all_fields
    type_map = defaultdict(lambda: 'number')
    type_map['Method'] = 'html'
    type_map['Language Model'] = type_map['Vision Model'] = 'html'
    type_map['OpenSource'] = type_map['Verified'] = 'str'
    check_box['type_map'] = type_map
    return df, check_box


def generate_table(results, fields):

    def get_mmbench_v11(item):
        assert 'MMBench_TEST_CN_V11' in item and 'MMBench_TEST_EN_V11' in item
        val = (item['MMBench_TEST_CN_V11']['Overall'] + item['MMBench_TEST_EN_V11']['Overall']) / 2
        val = float(f'{val:.1f}')
        return val

    res = defaultdict(list)
    for i, m in enumerate(results):
        item = results[m]
        meta = item['META']
        for k in META_FIELDS:
            if k == 'Param (B)':
                param = meta['Parameters']
                res[k].append(float(param.replace('B', '')) if param != '' else None)
            elif k == 'Method':
                name, url = meta['Method']
                res[k].append(f'<a href="{url}">{name}</a>')
                res['name'].append(name)
            else:
                res[k].append(meta[k])
        scores, ranks = [], []
        for d in fields:
            key_name = 'Overall' if d != 'OCRBench' else 'Final Score'
            # Every Model should have MMBench_V11 results
            if d == 'MMBench_V11':
                val = get_mmbench_v11(item)
                res[d].append(val)
                scores.append(val)
                ranks.append(nth_large(val, [get_mmbench_v11(x) for x in results.values()]))
            elif d in item:
                res[d].append(item[d][key_name])
                if d == 'MME':
                    scores.append(item[d][key_name] / 28)
                elif d == 'OCRBench':
                    scores.append(item[d][key_name] / 10)
                else:
                    scores.append(item[d][key_name])
                ranks.append(nth_large(item[d][key_name], [x[d][key_name] for x in results.values() if d in x]))
            else:
                res[d].append(None)
                scores.append(None)
                ranks.append(None)

        res['Avg Score'].append(round(np.mean(scores), 1) if None not in scores else None)
        res['Avg Rank'].append(round(np.mean(ranks), 2) if None not in ranks else None)

    df = pd.DataFrame(res)
    valid, missing = df[~pd.isna(df['Avg Score'])], df[pd.isna(df['Avg Score'])]
    valid = valid.sort_values('Avg Score')
    valid = valid.iloc[::-1]
    if len(fields):
        missing = missing.sort_values('MMBench_V11' if 'MMBench_V11' in fields else fields[0])
        missing = missing.iloc[::-1]
    df = pd.concat([valid, missing])
    return df
