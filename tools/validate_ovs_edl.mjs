// Run the pinned, unmodified upstream OVS validator. Node 24+ strips TS types.
import {readFileSync} from 'node:fs';
import {validateEdl} from '../integrations/orkas-video-studio/packages/core/src/ir/edl.ts';
const plan = JSON.parse(readFileSync(process.argv[2], 'utf8').replace(/^\uFEFF/, ''));
const result = validateEdl(plan);
process.stdout.write(JSON.stringify(result, null, 2) + '\n');
process.exitCode = result.ok ? 0 : 2;
