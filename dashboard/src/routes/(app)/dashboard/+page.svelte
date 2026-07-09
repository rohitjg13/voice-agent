<script lang="ts">
	let { data } = $props();

	const o = $derived(data.overview);
	const maxCalls = $derived(Math.max(1, ...data.timeseries.map((d) => d.calls)));

	const stats = $derived([
		{ label: 'calls / 30d', value: String(o.total_calls) },
		{ label: 'booked', value: String(o.booked) },
		{ label: 'book rate', value: `${(o.book_rate * 100).toFixed(1)}%` },
		{ label: 'talk minutes', value: o.total_minutes.toFixed(0) }
	]);

	function fmtDuration(s: number | null): string {
		if (s == null) return '—';
		return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
	}
</script>

<svelte:head><title>Overview — Coldline</title></svelte:head>

<h1 class="text-2xl font-bold tracking-tight">Overview</h1>
<p class="mt-1 text-sm text-muted">Last 30 days across every agent and campaign.</p>

<div class="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
	{#each stats as s (s.label)}
		<div class="card p-5">
			<div class="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">{s.label}</div>
			<div class="stat-num mt-2">{s.value}</div>
		</div>
	{/each}
</div>

<div class="mt-6 grid gap-6 lg:grid-cols-3">
	<div class="card p-5 lg:col-span-2">
		<div class="mb-4 flex items-baseline justify-between">
			<h2 class="font-semibold">Calls per day</h2>
			<span class="font-mono text-[11px] text-muted">■ calls · <span class="text-phos">■ booked</span></span>
		</div>
		{#if data.timeseries.length === 0}
			<p class="py-10 text-center text-sm text-muted">No calls yet — publish an agent and start a campaign.</p>
		{:else}
			<svg viewBox="0 0 600 160" class="w-full" role="img" aria-label="Calls per day">
				{#each data.timeseries as d, i (d.day)}
					{@const w = 600 / data.timeseries.length}
					{@const h = (d.calls / maxCalls) * 140}
					{@const hb = (d.booked / maxCalls) * 140}
					<rect x={i * w + 2} y={150 - h} width={Math.max(2, w - 4)} height={h} fill="#2e323b" rx="2" />
					<rect x={i * w + 2} y={150 - hb} width={Math.max(2, w - 4)} height={hb} fill="#6fc991" rx="2" />
				{/each}
			</svg>
		{/if}
	</div>
	<div class="card p-5">
		<h2 class="mb-4 font-semibold">Top objections</h2>
		{#if o.top_objections.length === 0}
			<p class="text-sm text-muted">None recorded yet.</p>
		{:else}
			<ul class="space-y-3">
				{#each o.top_objections as obj (obj.objection)}
					<li class="flex items-center justify-between text-sm">
						<span class="font-mono">{obj.objection}</span>
						<span class="font-mono text-amber">{obj.count}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>

<div class="card mt-6 overflow-x-auto">
	<div class="flex items-center justify-between px-4 pt-4">
		<h2 class="font-semibold">Recent calls</h2>
		<a class="font-mono text-[12px] text-phos hover:underline" href="/calls">view all →</a>
	</div>
	<table class="mt-2 w-full">
		<thead>
			<tr>
				<th class="th">Number</th><th class="th">Outcome</th><th class="th">Duration</th><th class="th">When</th>
			</tr>
		</thead>
		<tbody>
			{#each data.recent as c (c.id)}
				<tr class="row-hover">
					<td class="td font-mono">{c.customer_number ?? '—'}</td>
					<td class="td">
						<span class="font-mono text-[12px] {c.outcome === 'booked' ? 'text-phos' : c.outcome === 'failed' ? 'text-danger' : 'text-muted'}">
							{c.outcome ?? '—'}
						</span>
					</td>
					<td class="td font-mono">{fmtDuration(c.duration_seconds)}</td>
					<td class="td text-muted">{c.created_at ? new Date(c.created_at).toLocaleString() : '—'}</td>
				</tr>
			{:else}
				<tr><td class="td text-muted" colspan="4">No calls yet.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
