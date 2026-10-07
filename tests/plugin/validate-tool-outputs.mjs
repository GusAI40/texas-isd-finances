import Ajv from 'ajv/dist/2020.js';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

const inputPath = process.argv[2];
if (!inputPath) throw new Error('usage: node validate-tool-outputs.mjs <cases.json>');

const bundle = JSON.parse(readFileSync(resolve(inputPath), 'utf8'));
if (!Array.isArray(bundle.cases) || bundle.cases.length === 0) {
  throw new Error('validation bundle must contain at least one case');
}

const ajv = new Ajv({strict: true, allErrors: true, validateFormats: false});
const validators = new Map();

for (const testCase of bundle.cases) {
  const {label, schema, payload, valid = true} = testCase;
  if (!label || !schema) throw new Error('each validation case needs a label and schema');
  const schemaKey = JSON.stringify(schema);
  let validate = validators.get(schemaKey);
  if (!validate) {
    validate = ajv.compile(schema);
    validators.set(schemaKey, validate);
  }
  const actual = validate(payload);
  if (actual !== valid) {
    throw new Error(
      `${label}: expected valid=${valid}, received valid=${actual}: ${ajv.errorsText(validate.errors)}`,
    );
  }
}

console.log(`PASS: strict AJV recursively validated ${bundle.cases.length} tool-output cases`);
