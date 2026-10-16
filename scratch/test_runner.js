
global.window = { addEventListener: () => {} };
global.document = { addEventListener: () => {}, getElementById: () => ({ addEventListener: () => {}, querySelector: () => null, querySelectorAll: () => [] }) };
global.localStorage = { getItem: () => null, setItem: () => {} };
require('./scratch/temp_ingestion.js');
