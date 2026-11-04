// Parse an API datetime as UTC. Backend sends ISO 8601 with 'Z'; legacy naive
// strings (no offset) are treated as UTC. Never appends a second 'Z'.
export function parseUtc(value) {
	if (!value) return null;
	if (value instanceof Date) return value;
	const s = String(value);
	return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}
