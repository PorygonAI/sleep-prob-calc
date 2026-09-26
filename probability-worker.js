'use strict';
importScripts('probability.js');

let stylesPromise;
function loadStyles() {
    if (!stylesPromise) {
        stylesPromise = fetch('lapis_lakeside_sleep_styles.csv', {cache: 'no-store'})
            .then(response => {
                if (!response.ok) throw new Error(`睡姿数据读取失败（${response.status}），请稍后重试。`);
                return response.text();
            })
            .then(SleepProbability.parseCSV)
            .catch(error => { stylesPromise = null; throw error; });
    }
    return stylesPromise;
}

self.onmessage = async ({data}) => {
    try {
        const styles = await loadStyles();
        self.postMessage({id: data.id, ...SleepProbability.calculateCurve(styles, data)});
    } catch (error) {
        self.postMessage({id: data.id, error: error.message || '概率计算失败，请重试。'});
    }
};
