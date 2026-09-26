'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const engine = require('../probability.js');

const styles = [
    {internalId: 1, pokemonId: 280, level: 0, belly: false, leaderExclusion: true, spo: 2},
    {internalId: 2, pokemonId: 281, level: 0, belly: true, leaderExclusion: false, spo: 3},
    {internalId: 3, pokemonId: 282, level: 0, belly: true, leaderExclusion: false, spo: 5},
    {internalId: 4, pokemonId: 52, level: 0, belly: false, leaderExclusion: false, spo: 3},
    {internalId: 5, pokemonId: 280, level: 1, belly: false, leaderExclusion: false, spo: 3},
    {internalId: 6, pokemonId: 282, level: 0, belly: false, leaderExclusion: false, spo: 8}
];

// Independent exhaustive path enumeration, without DP/grouping.
function enumerate(pool, slots, gauge, belly, target) {
    const stack = [{slots, gauge, belly, weight: 1}];
    let probability = 0;
    while (stack.length) {
        const state = stack.pop();
        if (!state.slots) continue;
        let candidates = pool.filter(style => style.spo <= state.gauge && (state.belly || !style.belly));
        if (state.slots === 1) candidates = candidates.filter(style => !style.leaderExclusion);
        if (!candidates.length) {
            probability += state.weight * (target === 280 ? 1 - Math.pow(9 / 10, state.slots) : 0);
            continue;
        }
        if (state.slots === 1) {
            candidates.sort((a, b) => b.spo - a.spo || a.level - b.level || a.internalId - b.internalId);
            probability += state.weight * Number(candidates[0].pokemonId === target);
            continue;
        }
        for (const style of candidates) {
            const weight = state.weight / candidates.length;
            if (style.pokemonId === target) probability += weight;
            else stack.push({slots: state.slots - 1, gauge: state.gauge - style.spo,
                belly: state.belly && !style.belly, weight});
        }
    }
    return probability;
}

test('DP matches exhaustive draws: ties, exclusions, belly state, repeats, unlocks and exact costs', () => {
    for (const target of [280, 281, 282]) {
        for (const level of [0, 1]) {
            const table = engine.computeLevel(styles, level, 4, 40, target);
            for (let slots = 0; slots <= 4; slots++) {
                for (let belly = 0; belly <= 1; belly++) {
                    for (let gauge = 0; gauge <= 40; gauge++) {
                        const expected = enumerate(styles.filter(style => style.level <= level), slots, gauge, belly, target);
                        assert.ok(Math.abs(table[slots][belly][gauge] - expected) < 1e-12,
                            `${target}/${level}/${slots}/${belly}/${gauge}`);
                    }
                }
            }
        }
    }
});

test('no-energy pool contains Ralts only', () => {
    for (const target of [280, 281, 282]) {
        const table = engine.computeLevel([], 0, 8, 1, target);
        for (let slots = 0; slots <= 8; slots++) {
            assert.equal(table[slots][1][0], target === 280 ? 1 - 0.9 ** slots : 0);
        }
    }
});

test('last draw chooses lowest level, then lowest internalId at equal SPO', () => {
    const tied = [
        {internalId: 9, pokemonId: 280, level: 0, spo: 4},
        {internalId: 1, pokemonId: 281, level: 1, spo: 4},
        {internalId: 8, pokemonId: 282, level: 0, spo: 4}
    ];
    assert.equal(engine.computeLevel(tied, 1, 1, 4, 282)[1][1][4], 1);
    assert.equal(engine.computeLevel(tied, 1, 1, 4, 280)[1][1][4], 0);
});

test('rank and slot thresholds include boundary values and former gaps', () => {
    assert.equal(engine.getRankId(12937), 0);
    assert.equal(engine.getRankId(12938), 1);
    assert.equal(engine.getRankId(5193272), 34);
    const thresholds = [3153520, 7730435, 16659808, 30491710, 68664246];
    thresholds.forEach((value, index) => {
        assert.equal(engine.getSleepPoseCount(value - 1), index + 3);
        assert.equal(engine.getSleepPoseCount(value), index + 4);
    });
});

test('strict inputs support default, single score and Chinese comma', () => {
    assert.deepEqual(engine.parseInput('0', ''), {power: 0, start: 1, end: 100});
    assert.deepEqual(engine.parseInput('100', '50，50'), {power: 100, start: 50, end: 50});
    for (const value of ['', '-1', '1.5', '1x', 'Infinity', '9007199254740991']) {
        assert.throws(() => engine.parseInput(value, ''));
    }
    for (const range of ['0,100', '1,101', '50,1', '1.5,20', '1,20x', '1,2,3']) {
        assert.throws(() => engine.parseInput('100', range));
    }
});

test('CSV handles BOM, quoted names, CRLF and rejects invalid data', () => {
    const header = 'internalId,pokemon_id,level_order,is_on_snorlax,is_leader_exclusion,spo,pokemon_name\r\n';
    const text = '\uFEFF' + header + '1,280,0,false,false,8,"a,b"\r\n2,281,4,0,1,122,"c""d"\r\n3,282,15,true,false,548,"e\nf"';
    assert.equal(engine.parseCSV(text).length, 3);
    assert.throws(() => engine.parseCSV(text.replace(',548,', ',-1,')));
    assert.throws(() => engine.parseCSV(text.replace(',true,', ',unknown,')));
    assert.throws(() => engine.parseCSV(text + '\r\n1,280,0,false,false,8,name'));
    assert.throws(() => engine.parseCSV('<html>error</html>'));
});

test('real CSV curves stay finite for all targets, including large energies', () => {
    const realStyles = engine.parseCSV(fs.readFileSync(path.join(__dirname, '../lapis_lakeside_sleep_styles.csv'), 'utf8'));
    for (const pokemonId of [280, 281, 282]) {
        for (const power of [0, 71156, 675330, 5193272, 100000000]) {
            const curve = engine.calculateCurve(realStyles, {power, start: 1, end: 100, pokemonId});
            assert.equal(curve.probabilities.length, 100);
            assert.ok(curve.probabilities.every(p => Number.isFinite(p) && p >= 0 && p <= 1));
        }
    }
    for (const pokemonId of [281, 282]) {
        const curve = engine.calculateCurve(realStyles, {power: 1000, start: 1, end: 100, pokemonId});
        assert.ok(curve.probabilities.every(p => p === 0));
    }
});

test('large-energy saturation equals uncapped DP', () => {
    const maxSlots = 8;
    for (const pokemonId of [280, 281, 282]) {
        const full = engine.computeLevel(styles, 1, maxSlots, 120, pokemonId);
        const capped = engine.computeLevel(styles, 1, maxSlots, 64, pokemonId);
        for (let gauge = 64; gauge <= 120; gauge++) {
            assert.equal(full[8][1][gauge], capped[8][1][64]);
        }
    }
});
