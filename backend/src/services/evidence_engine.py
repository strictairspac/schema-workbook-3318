"""取证包生成：在抽检样本中找到能推翻草案依赖的最少原始行。

给定关系属性、函数依赖、一批原始行与行数上限：
1. 对每条（原子化后的）函数依赖，找出整批样本中能推翻它的原始行对；
2. 只针对确实能被整批样本推翻的依赖求解；
3. 精确搜索最小的行集合，使每条可推翻依赖都有一对行落在集合内；
4. 只有证明最少行数不超过上限时才给出可发布的取证包；证明超限才报“装不下”。
搜索预算用尽时如实报失败，绝不把未证明的结果当成最少或超限。
"""
import hashlib
import json

MAX_SAMPLE_ROWS = 60
MAX_ROW_LIMIT = 60
SEARCH_BUDGET = 2_000_000  # 单个取证包精确搜索的节点预算


class SearchBudgetExceeded(Exception):
    pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def rules_fingerprint(attributes, dependencies):
    """草案规则的确定性指纹；属性或依赖任一变化都会换指纹。"""
    atoms = sorted({(tuple(sorted(dep['lhs'])), rhs) for dep in dependencies for rhs in dep['rhs']})
    payload = {'attributes': sorted(set(attributes)), 'dependencies': atoms}
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _atomic_dependencies(dependencies):
    atoms = []
    for index, dep in enumerate(dependencies):
        lhs = sorted(dep['lhs'])
        for rhs in dep['rhs']:
            atoms.append({'dependency_index': index, 'lhs': lhs, 'rhs': rhs})
    return atoms


def _refuting_pairs(columns, rows, lhs, rhs):
    """返回所有 (i, j)：在 lhs 上相等、在 rhs 上不同，且 i<j。"""
    if rhs in lhs:
        return []
    lhs_columns = [columns.index(attribute) for attribute in lhs]
    pairs = []
    for i in range(len(rows)):
        left = rows[i]
        for j in range(i + 1, len(rows)):
            right = rows[j]
            if left[rhs] == right[rhs]:
                continue
            if all(left[columns[c]] == right[columns[c]] for c in lhs_columns):
                pairs.append((i, j))
    return pairs


def _constraints(columns, rows, atoms):
    """按 (lhs, rhs) 合并重复依赖；一个约束被一对行推翻即可同时证明多个重复依赖。"""
    keyed = {}
    for atom in atoms:
        key = (tuple(atom['lhs']), atom['rhs'])
        constraint = keyed.get(key)
        if constraint is None:
            constraint = {
                'lhs': list(atom['lhs']),
                'rhs': atom['rhs'],
                'atoms': [],
                'pairs': _refuting_pairs(columns, rows, atom['lhs'], atom['rhs']),
            }
            keyed[key] = constraint
        constraint['atoms'].append(atom)
    return list(keyed.values())


def _greedy_cover(constraints, pair_cover):
    """贪心给出一个合法行集合，作为最小性搜索的上界。"""
    uncovered = set(range(len(constraints)))
    chosen = set()
    while uncovered:
        best_pair = None
        best_gain = -1
        for pair in sorted(pair_cover):
            gain = len(pair_cover[pair] & uncovered)
            if gain > best_gain:
                best_gain, best_pair = gain, pair
        if not best_gain:
            break
        chosen.update(best_pair)
        uncovered -= pair_cover[best_pair]
    return chosen, uncovered


def _search(constraints, limit, stats):
    """精确判定是否存在不超过 limit 行的覆盖；返回行集合、None（已证明不存在）或抛预算异常。"""
    pair_sets = [set(constraint['pairs']) for constraint in constraints]
    pair_cover = {}
    for index, pairs in enumerate(pair_sets):
        for pair in pairs:
            pair_cover.setdefault(pair, set()).add(index)

    if not constraints:
        return set()
    upper, leftover = _greedy_cover(constraints, pair_cover)
    stats['upper_bound_rows'] = len(upper)
    if leftover:  # 理论不可达：每个约束都有反例行对
        raise RuntimeError('内部错误：存在无法覆盖的依赖约束')

    upper_bound = len(upper)
    if limit < 2:
        return None
    stop = min(upper_bound, limit)
    if stop < 2:
        return None
    nodes = [0]
    all_constraints = frozenset(range(len(constraints)))

    def search_at(k):
        memo = set()

        def covered(state):
            result = set()
            for pair, targets in pair_cover.items():
                if pair[0] in state and pair[1] in state:
                    result |= targets
            return result

        def recurse(state, uncovered):
            nodes[0] += 1
            if nodes[0] > SEARCH_BUDGET:
                raise SearchBudgetExceeded()
            if not uncovered:
                return state
            remaining = k - len(state)
            if remaining <= 0:
                return None
            key = (frozenset(state), frozenset(uncovered))
            if key in memo:
                return None
            best = None
            best_min_add = None
            for index in uncovered:
                min_add = min(len({a, b} - state) for a, b in pair_sets[index])
                if min_add > remaining:
                    memo.add(key)
                    return None
                if best is None or min_add < best_min_add or (
                        min_add == best_min_add and len(pair_sets[index]) < len(pair_sets[best])):
                    best, best_min_add = index, min_add
            ordered = sorted(pair_sets[best], key=lambda p: (len(set(p) - state), p))
            seen_next = set()
            for pair in ordered:
                added = frozenset(set(pair) - state)
                if len(added) > remaining:
                    continue
                next_state = frozenset(set(state) | set(pair))
                if next_state in seen_next:
                    continue
                seen_next.add(next_state)
                next_covered = covered(next_state)
                next_uncovered = frozenset(index for index in uncovered if index not in next_covered)
                found = recurse(next_state, next_uncovered)
                if found is not None:
                    return found
            memo.add(key)
            return None

        return recurse(frozenset(), all_constraints)

    for k in range(2, stop + 1):
        stats['iterations'] = stats.get('iterations', 0) + 1
        found = search_at(k)
        if found is not None:
            stats['nodes'] = nodes[0]
            return set(found)
        if k == upper_bound:
            break  # 贪心上界本身合法，不可能再失败
    stats['nodes'] = nodes[0]
    return None if upper_bound > limit else set(upper)


def _pair_view(rows, columns, pair):
    i, j = pair
    return {
        'row_numbers': [i + 1, j + 1],
        'rows': [
            {'row_number': i + 1, 'values': {column: rows[i][column] for column in columns}},
            {'row_number': j + 1, 'values': {column: rows[j][column] for column in columns}},
        ],
    }


def build_package(attributes, dependencies, columns, rows, row_limit,
                  sample_version, fingerprint):
    """纯函数：由冻结的草案规则与样本行生成取证包内容。"""
    attributes = list(dict.fromkeys(attributes))
    columns = list(columns)
    atoms = _atomic_dependencies(dependencies)
    constraints = _constraints(columns, rows, atoms)
    refutable = [c for c in constraints if c['pairs']]
    non_refutable = [c for c in constraints if not c['pairs']]

    stats = {'sample_rows': len(rows), 'refutable_dependencies': len(refutable),
             'search_budget': SEARCH_BUDGET}
    result = {
        'attributes': attributes,
        'row_limit': row_limit,
        'sample_version': sample_version,
        'rules_fingerprint': fingerprint,
        'refutable_dependencies': [],
        'non_refutable_dependencies': [],
        'witness_rows': [],
        'witness_row_count': 0,
        'minimal': True,
        'infeasible': False,
        'method': '对每条可推翻依赖精准枚举反例原始行对，再精确搜索覆盖全部反例的最少行集合',
    }

    try:
        chosen = _search(refutable, row_limit, stats)
        unproven = False
    except SearchBudgetExceeded:
        # 未能在预算内证明；不谎报“最少”，也不谎报“超限”，只供核对、禁止发布。
        chosen, unproven = None, True

    if chosen is None and not unproven:
        result.update({
            'infeasible': True,
            'required_rows_at_least': row_limit + 1,
            'reason': f'已证明至少需要超过 {row_limit} 行原始行；行数上限 {row_limit} 装不下',
            'search': stats,
        })
        for constraint in sorted(refutable, key=lambda c: (c['lhs'], c['rhs'])):
            result['refutable_dependencies'].append({
                'lhs': constraint['lhs'], 'rhs': constraint['rhs'],
                'dependency_indexes': sorted({a['dependency_index'] for a in constraint['atoms']}),
                'candidate_pair_count': len(constraint['pairs']),
                'witness_pair': None,
            })
    elif unproven:
        result.update({
            'minimal': False,
            'unproven': True,
            'reason': '精确最小化搜索超出预算，未能证明最少行数与是否超限；可缩小样本或减少依赖后重试',
            'search': stats,
        })
        for constraint in sorted(refutable, key=lambda c: (c['lhs'], c['rhs'])):
            result['refutable_dependencies'].append({
                'lhs': constraint['lhs'], 'rhs': constraint['rhs'],
                'dependency_indexes': sorted({a['dependency_index'] for a in constraint['atoms']}),
                'candidate_pair_count': len(constraint['pairs']),
                'witness_pair': None,
            })
    else:
        # 只保留真正用于举证的原始行；搜索已证明不存在更小集合。
        used = set()
        evidence = []
        for constraint in sorted(refutable, key=lambda c: (c['lhs'], c['rhs'])):
            pair = next(p for p in sorted(constraint['pairs']) if p[0] in chosen and p[1] in chosen)
            used.update(pair)
            single = _pair_view(rows, columns, pair)
            left, right = single['rows']
            evidence.append({
                'lhs': constraint['lhs'], 'rhs': constraint['rhs'],
                'dependency_indexes': sorted({a['dependency_index'] for a in constraint['atoms']}),
                'candidate_pair_count': len(constraint['pairs']),
                'lhs_values': {attribute: left['values'][attribute] for attribute in constraint['lhs']},
                'rhs_values': [left['values'][constraint['rhs']], right['values'][constraint['rhs']]],
                'witness_pair': single,
            })
        witness = sorted(used)
        if len(witness) < len(chosen):
            # 展示行对已足够覆盖全部依赖，行数只会更少，仍不劣于已证明的最小值。
            stats['display_rows'] = len(witness)
        result['refutable_dependencies'] = evidence
        result['witness_rows'] = [
            {'row_number': index + 1, 'values': {column: rows[index][column] for column in columns}}
            for index in witness
        ]
        result['witness_row_count'] = len(witness)
        result['search'] = stats

    for constraint in sorted(non_refutable, key=lambda c: (c['lhs'], c['rhs'])):
        result['non_refutable_dependencies'].append({
            'lhs': constraint['lhs'], 'rhs': constraint['rhs'],
            'dependency_indexes': sorted({a['dependency_index'] for a in constraint['atoms']}),
        })

    payload = {key: value for key, value in result.items() if key != 'checksum'}
    result['checksum'] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return result
