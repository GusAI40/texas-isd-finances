import Ajv from 'ajv/dist/2020.js';
import {readFileSync, existsSync, statSync} from 'node:fs';
import {resolve, relative, sep} from 'node:path';

const root = resolve(process.argv[2] || '../../plugin');
const read = file => JSON.parse(readFileSync(resolve(root, file), 'utf8'));
const schema = name => JSON.parse(readFileSync(new URL(`./${name}.schema.json`, import.meta.url), 'utf8'));
const ajv = new Ajv({strict: false, allErrors: true});
function valid(file, schemaName) { const check = ajv.compile(schema(schemaName)); const value = read(file); if (!check(value)) throw new Error(`${file}: ${ajv.errorsText(check.errors)}`); return value; }
function inside(path) { const target = resolve(root, path); const rel = relative(root, target); if (!rel || rel.startsWith(`..${sep}`) || !existsSync(target)) throw new Error(`missing or escaping package reference: ${path}`); return target; }
const plugin = valid('plugin.json', 'plugin');
const mcp = valid('mcp.json', 'mcp');
if (plugin.extensions?.['com.openai']?.apps !== './.app.json') throw new Error('manifest must reference the generated app mapping');
const apps = read('.app.json').apps;
const mappings = Object.entries(apps || {});
if (mappings.length !== 1 || !/^dev-[0-9a-f]+$/.test(mappings[0][0]) || !/^asdk_app_[0-9a-f]+$/.test(mappings[0][1]?.id || '')) throw new Error('generated app mapping has an unexpected shape');
for (const server of Object.values(mcp.mcpServers)) if (server.type !== 'streamable-http' || server.url !== 'https://txisd.dev/mcp' || 'headers' in server) throw new Error('MCP server must be the public no-auth Streamable HTTP endpoint');
for (const dir of ['skills', 'assets']) { const path = inside(`./${dir}`); if (!statSync(path).isDirectory()) throw new Error(`${dir} must be a directory`); }
const skill = readFileSync(inside('./skills/district-report/SKILL.md'), 'utf8'); if (!skill.startsWith('---\n') || !skill.includes('\nname: district-report\n')) throw new Error('district-report skill frontmatter is invalid');
if (JSON.stringify(plugin).match(/plugin_asdk_app_|chat\.openai\.com\/c\//i)) throw new Error('package must not contain private registration or conversation data');
console.log('PASS: official Agent Plugins schemas, public endpoint, references, and skill');
