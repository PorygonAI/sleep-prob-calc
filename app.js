'use strict';

const result = document.getElementById('result');
const buttons = [...document.querySelectorAll('button')];
let selectedPokemon = 280;
let worker;
let requestId = 0;

function setBusy(busy) {
    buttons.forEach(button => { button.disabled = busy; });
    document.querySelector('.container').setAttribute('aria-busy', String(busy));
}

function showCurve({scores, probabilities}) {
    const pokemon = SleepProbability.POKEMON[selectedPokemon];
    const maxProb = Math.max(...probabilities);
    const bestPoint = scores[probabilities.indexOf(maxProb)];
    result.textContent = `${pokemon}概率最高的分数是${bestPoint}，概率为${maxProb.toPrecision(6)}`;
    if (window.probChartInstance) window.probChartInstance.destroy();
    const canvas = document.getElementById('probChart');
    canvas.setAttribute('aria-label', `${pokemon}在分数 ${scores[0]}～${scores.at(-1)} 的出现概率曲线`);
    window.probChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: scores,
            datasets: [{
                label: `${pokemon}概率曲线`, data: probabilities,
                borderColor: '#2E86AB', borderWidth: 2, fill: false, tension: 0.1,
                pointRadius: 3, pointHitRadius: 6, pointBackgroundColor: '#2E86AB',
                pointBorderWidth: 0, pointBorderColor: '#fff'
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: {mode: 'index', intersect: false, axis: 'x'},
            plugins: {
                tooltip: {
                    enabled: true, backgroundColor: 'rgba(0,0,0,0.7)',
                    titleFont: {size: 14}, bodyFont: {size: 12}, padding: 10,
                    callbacks: {label: context => `分数 ${context.label}：概率 ${context.raw.toPrecision(6)}`}
                },
                legend: {position: 'top', labels: {font: {size: 14}}}
            },
            scales: {
                x: {
                    title: {display: true, text: '分数'},
                    ticks: {
                        autoSkip: false, maxTicksLimit: 20,
                        maxRotation: 45, minRotation: 30, padding: 8,
                        callback: function (value) {
                            const label = this.getLabelForValue(value);
                            return Number(label) % 5 === 0 || scores.length === 1 ? label : null;
                        }
                    },
                    grid: {display: true, alpha: 0.3}
                },
                y: {title: {display: true, text: '概率'}, min: 0, grid: {display: true, alpha: 0.3}}
            }
        }
    });
}

function getWorker() {
    if (!worker) {
        worker = new Worker('probability-worker.js');
        worker.onmessage = ({data}) => {
            if (data.id !== requestId) return;
            setBusy(false);
            if (data.error) result.textContent = data.error;
            else {
                try { showCurve(data); }
                catch (error) { result.textContent = `绘图失败：${error.message}`; }
            }
        };
        worker.onerror = () => {
            result.textContent = '计算程序加载失败，请刷新页面后重试。';
            setBusy(false);
            worker.terminate();
            worker = null;
        };
    }
    return worker;
}

function calculateProb(pokemonId = selectedPokemon) {
    try {
        const input = SleepProbability.parseInput(
            document.getElementById('power').value,
            document.getElementById('xRange').value
        );
        selectedPokemon = pokemonId;
        document.querySelectorAll('[data-pokemon]').forEach(button => {
            button.setAttribute('aria-pressed', String(Number(button.dataset.pokemon) === pokemonId));
        });
        // Clear old output so a failed/new calculation never displays an unrelated curve.
        if (window.probChartInstance) {
            window.probChartInstance.destroy();
            window.probChartInstance = null;
        }
        result.textContent = `正在计算${SleepProbability.POKEMON[pokemonId]}的概率…`;
        setBusy(true);
        getWorker().postMessage({...input, pokemonId, id: ++requestId});
    } catch (error) {
        setBusy(false);
        result.textContent = error.message;
    }
}

document.querySelectorAll('[data-pokemon]').forEach(button => {
    button.addEventListener('click', () => calculateProb(Number(button.dataset.pokemon)));
});
document.getElementById('calculate').addEventListener('click', () => calculateProb());
document.querySelectorAll('input').forEach(input => {
    input.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !document.getElementById('calculate').disabled) calculateProb();
    });
});
