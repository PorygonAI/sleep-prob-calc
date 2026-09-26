/* Browser/Node shared probability engine. No precomputed probability files. */
(function (root) {
    'use strict';

    const POKEMON = {280: '拉鲁拉丝', 281: '奇鲁莉安', 282: '沙奈朵'};
    const RANK_THRESHOLDS = [
        0, 12938, 29756, 48515, 71156, 97031, 130668, 171420, 219936,
        272333, 328610, 388122, 452809, 522025, 596086, 675330, 760123,
        850851, 958702, 1075709, 1202596, 1340143, 1489190, 1650645,
        1825483, 2014758, 2219603, 2441243, 2680993, 2925574, 3188730,
        3454577, 3739033, 4166848, 5193272
    ];
    const SLOT_THRESHOLDS = [3153520, 7730435, 16659808, 30491710, 68664246];

    function getRankId(power) {
        return RANK_THRESHOLDS.filter(threshold => power >= threshold).length - 1;
    }

    function getSleepPoseCount(power) {
        // Use lower bounds so the few gaps in the old ranges remain calculable.
        return 3 + SLOT_THRESHOLDS.filter(threshold => power >= threshold).length;
    }

    function parseInput(powerText, rangeText) {
        const power = Number(powerText);
        if (!String(powerText).trim() || !Number.isSafeInteger(power) || power < 0 ||
            !Number.isSafeInteger(power * 100)) {
            throw new Error('卡比兽能量必须是有效的非负整数！');
        }
        const range = rangeText.trim() || '1,100';
        const match = range.match(/^(\d+)\s*[,，]\s*(\d+)$/);
        if (!match || +match[1] < 1 || +match[2] > 100 || +match[1] > +match[2]) {
            throw new Error('分数范围请输入 1～100 内的整数，如 1,100。');
        }
        return {power, start: +match[1], end: +match[2]};
    }

    function parseCSV(text) {
        // Support BOM, CRLF, quoted commas/newlines and escaped quotes.
        const rows = [];
        let row = [], field = '', quoted = false;
        text = text.replace(/^\uFEFF/, '');
        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            if (char === '"') {
                if (quoted && text[i + 1] === '"') { field += '"'; i++; }
                else quoted = !quoted;
            } else if (!quoted && (char === ',' || char === '\n' || char === '\r')) {
                row.push(field);
                field = '';
                if (char !== ',') {
                    if (row.some(value => value !== '')) rows.push(row);
                    row = [];
                    if (char === '\r' && text[i + 1] === '\n') i++;
                }
            } else field += char;
        }
        if (quoted) throw new Error('睡姿 CSV 引号未闭合。');
        row.push(field);
        if (row.some(value => value !== '')) rows.push(row);
        const headers = rows.shift() || [];
        const required = ['internalId', 'pokemon_id', 'level_order', 'is_on_snorlax', 'is_leader_exclusion', 'spo'];
        if (!rows.length || required.some(key => !headers.includes(key))) {
            throw new Error('睡姿 CSV 为空或缺少必要字段。');
        }
        const ids = new Set();
        const styles = rows.map(values => {
            if (values.length !== headers.length) throw new Error('睡姿 CSV 列数不正确。');
            const value = key => values[headers.indexOf(key)].trim();
            const integer = key => {
                if (!/^\d+$/.test(value(key)) || !Number.isSafeInteger(+value(key))) {
                    throw new Error(`睡姿 CSV 数值无效：${key}`);
                }
                return +value(key);
            };
            const boolean = key => {
                const raw = value(key).toLowerCase();
                if (!['true', 'false', '0', '1'].includes(raw)) throw new Error(`睡姿 CSV 布尔值无效：${key}`);
                return raw === 'true' || raw === '1';
            };
            const style = {
                internalId: integer('internalId'), pokemonId: integer('pokemon_id'),
                level: integer('level_order'), belly: boolean('is_on_snorlax'),
                leaderExclusion: boolean('is_leader_exclusion'), spo: integer('spo')
            };
            if (style.level > 34 || !style.pokemonId || ids.has(style.internalId)) {
                throw new Error('睡姿 CSV 包含无效或重复睡姿。');
            }
            ids.add(style.internalId);
            return style;
        });
        if (Object.keys(POKEMON).some(id => !styles.some(style => style.pokemonId === +id))) {
            throw new Error('睡姿 CSV 缺少目标宝可梦。');
        }
        return styles;
    }

    function noEnergyProbability(slots, pokemonId) {
        // Preserve the original fixed ten-style Balanced pool: one Ralts,
        // no Kirlia/Gardevoir. This is a model assumption, not inferred from CSV.
        return pokemonId === 280 ? 1 - 0.9 ** slots : 0;
    }

    function makeTransition(styles, belly, maxGauge, pokemonId) {
        const count = new Uint32Array(maxGauge + 1);
        const target = new Uint32Array(maxGauge + 1);
        const grouped = new Map();
        const pool = styles.filter(style => (belly || !style.belly) && style.spo <= maxGauge);
        for (const style of pool) {
            count[style.spo]++;
            if (style.pokemonId === pokemonId) target[style.spo]++;
            else {
                const nextBelly = style.belly ? 0 : belly;
                const key = `${style.spo}:${nextBelly}`;
                if (!grouped.has(key)) grouped.set(key, {cost: style.spo, nextBelly, count: 0});
                grouped.get(key).count++;
            }
        }
        for (let gauge = 1; gauge <= maxGauge; gauge++) {
            count[gauge] += count[gauge - 1];
            target[gauge] += target[gauge - 1];
        }
        const last = new Float64Array(maxGauge + 1).fill(noEnergyProbability(1, pokemonId));
        const candidates = pool.filter(style => !style.leaderExclusion).sort((a, b) =>
            a.spo - b.spo || a.level - b.level || a.internalId - b.internalId);
        for (let i = 0; i < candidates.length;) {
            const best = candidates[i];
            let next = i + 1;
            while (next < candidates.length && candidates[next].spo === best.spo) next++;
            const end = next < candidates.length ? candidates[next].spo : maxGauge + 1;
            last.fill(best.pokemonId === pokemonId ? 1 : 0, best.spo, end);
            i = next;
        }
        return {count, target, groups: [...grouped.values()], last};
    }

    function computeLevel(styles, level, maxSlots, maxGauge, pokemonId) {
        if (!POKEMON[pokemonId]) throw new Error('不支持的宝可梦。');
        const unlocked = styles.filter(style => style.level <= level);
        const transitions = [0, 1].map(belly => makeTransition(unlocked, belly, maxGauge, pokemonId));
        const probability = Array.from({length: maxSlots + 1}, () =>
            [new Float64Array(maxGauge + 1), new Float64Array(maxGauge + 1)]);
        if (maxSlots >= 1) probability[1] = transitions.map(transition => transition.last);
        for (let slots = 2; slots <= maxSlots; slots++) {
            for (let belly = 0; belly <= 1; belly++) {
                const transition = transitions[belly];
                const current = probability[slots][belly];
                current.set(transition.target);
                for (const {cost, nextBelly, count} of transition.groups) {
                    const previous = probability[slots - 1][nextBelly];
                    for (let gauge = cost; gauge <= maxGauge; gauge++) {
                        current[gauge] += count * previous[gauge - cost];
                    }
                }
                for (let gauge = 0; gauge <= maxGauge; gauge++) {
                    current[gauge] = transition.count[gauge]
                        ? Math.min(1, current[gauge] / transition.count[gauge])
                        : noEnergyProbability(slots, pokemonId);
                }
            }
        }
        return probability;
    }

    function calculateCurve(styles, {power, start, end, pokemonId}) {
        parseInput(String(power), `${start},${end}`);
        const level = getRankId(power);
        const scores = Array.from({length: end - start + 1}, (_, i) => start + i);
        const maxSlots = getSleepPoseCount(power * end);
        const maxCost = Math.max(0, ...styles.filter(style => style.level <= level).map(style => style.spo));
        // Above maxCost * slots, every draw can afford every style. The result
        // is constant, so large energies need no arbitrary SPO/file-size limit.
        const maxGauge = Math.min(Math.floor(power * end / 38000), maxCost * maxSlots);
        const probability = computeLevel(styles, level, maxSlots, maxGauge, pokemonId);
        const probabilities = scores.map(score => probability[getSleepPoseCount(power * score)][1][
            Math.min(Math.floor(power * score / 38000), maxGauge)
        ]);
        return {scores, probabilities};
    }

    const api = {POKEMON, parseCSV, parseInput, getRankId, getSleepPoseCount,
        noEnergyProbability, computeLevel, calculateCurve};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.SleepProbability = api;
})(globalThis);
