<script lang="ts">
	let { data } = $props();

	const filters = ['all', 'booked', 'completed', 'no_answer', 'voicemail', 'failed'];

	function fmtDuration(s: number | null): string {
		if (s == null) return '—';
		return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
	}
</script>

<svelte:head><title>Calls — Coldline</title></svelte:head>

<h1 class="text-2xl font-bold tracking-tight">Call log</h1>

<div class="mt-4 flex flex-wrap gap-2">
	{#each filters as f (f)}
		<a
			href={f === 'all' ? '/calls' : `/calls?outcome=${f}`}
			class="tab-pill {(data.outcome ?? 'all') === f ? 'tab-pill-active' : 'tab-pill-inactive'}"
		>
			{f}
		</a>
	{/each}
</div>

<div class="card mt-4 overflow-x-auto">
	<table class="w-full">
		<thead>
			<tr>
				<th class="th">Number</th><th class="th">Outcome</th><th class="th">Stage</th>
				<th class="th">Duration</th><th class="th">Summary</th><th class="th">When</th>
			</tr>
		</thead>
		<tbody>
			{#each data.calls as c (c.id)}
				<tr class="cursor-pointer row-hover" onclick={() => (location.href = `/calls/${c.id}`)}>
					<td class="td font-mono"><a href="/calls/{c.id}" class="hover:text-phos">{c.customer_number ?? '—'}</a></td>
					<td class="td font-mono text-[12px] {c.booked ? 'text-phos' : c.outcome === 'failed' ? 'text-danger' : 'text-muted'}">{c.outcome ?? '—'}</td>
					<td class="td font-mono text-[12px] text-muted">{c.stage_reached ?? '—'}</td>
					<td class="td font-mono">{fmtDuration(c.duration_seconds)}</td>
					<td class="td max-w-md truncate text-muted">{c.summary ?? ''}</td>
					<td class="td whitespace-nowrap text-muted">{c.created_at ? new Date(c.created_at).toLocaleString() : '—'}</td>
				</tr>
			{:else}
				<tr><td class="td text-muted" colspan="6">No calls match.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
