<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';

	let { data, form } = $props();

	const c = $derived(data.campaign);
	const pct = $derived(c.total_leads ? Math.round((c.done_leads / c.total_leads) * 100) : 0);

	$effect(() => {
		if (c.status !== 'running') return;
		const t = setInterval(() => invalidateAll(), 10_000);
		return () => clearInterval(t);
	});

	const statusColor: Record<string, string> = {
		queued: 'text-muted',
		calling: 'text-phos',
		completed: 'text-ink',
		failed: 'text-danger',
		no_answer: 'text-amber',
		dnc: 'text-danger'
	};
</script>

<svelte:head><title>{c.name} — Coldline</title></svelte:head>

<a class="font-mono text-[12px] text-muted hover:text-phos transition-colors" href="/campaigns">← campaigns</a>
<div class="mt-1 flex flex-wrap items-center justify-between gap-4">
	<div class="flex items-center gap-3">
		<h1 class="text-2xl font-bold tracking-tight">{c.name}</h1>
		<span class="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest
			{c.status === 'running' ? 'text-phos' : c.status === 'completed' ? 'text-muted' : 'text-amber'}">
			{#if c.status === 'running'}<span class="pulse-dot"></span>{/if}
			{c.status}
		</span>
	</div>
	<div class="flex gap-3">
		{#if c.status === 'running'}
			<form method="POST" action="?/pause" use:enhance>
				<button class="btn-ghost" type="submit">⏸ Pause</button>
			</form>
		{:else if c.status !== 'completed'}
			<form method="POST" action="?/start" use:enhance>
				<button class="btn" type="submit">▶ Start dialing</button>
			</form>
		{/if}
	</div>
</div>

{#if form?.error}
	<div class="flash-danger mt-4">{form.error}</div>
{/if}
{#if form?.report}
	<div class="flash-success mt-4">
		Imported {form.report.imported} leads{form.report.skipped.length
			? ` · ${form.report.skipped.length} skipped`
			: ''}.
	</div>
	{#if form.report.skipped.length}
		<details class="mt-2 text-sm text-muted">
			<summary class="cursor-pointer font-mono text-[12px]">skipped rows</summary>
			<ul class="mt-1 list-inside list-disc">
				{#each form.report.skipped as s (s.row)}
					<li>row {s.row}: {s.reason}</li>
				{/each}
			</ul>
		</details>
	{/if}
{/if}

<div class="card mt-6 p-5">
	<div class="flex items-center justify-between">
		<span class="font-mono text-[12px] text-muted">
			{c.done_leads}/{c.total_leads} done · {c.calling_leads} on the line
		</span>
		<span class="font-mono text-[12px] text-phos">{pct}%</span>
	</div>
	<div class="mt-2 h-2 overflow-hidden rounded-full" style="box-shadow: var(--shadow-inset-a), var(--shadow-inset-b);">
		<div class="h-full bg-phos transition-all rounded-full" style="width: {pct}%"></div>
	</div>
</div>

{#if c.status !== 'completed'}
	<form
		method="POST"
		action="?/upload"
		use:enhance
		enctype="multipart/form-data"
		class="card mt-4 flex items-center gap-3 p-4"
	>
		<span class="label mb-0">Add leads (CSV: phone, name, company, email)</span>
		<input class="input max-w-xs" type="file" name="file" accept=".csv" required />
		<button class="btn-ghost" type="submit">Upload</button>
	</form>
{/if}

<div class="card mt-4 overflow-x-auto">
	<table class="w-full">
		<thead>
			<tr>
				<th class="th">Lead</th><th class="th">Number</th><th class="th">Status</th>
				<th class="th">Attempts</th><th class="th">Error</th>
			</tr>
		</thead>
		<tbody>
			{#each c.leads as lead (lead.id)}
				<tr class="row-hover">
					<td class="td">{lead.name ?? '—'}{lead.company ? ` · ${lead.company}` : ''}</td>
					<td class="td font-mono">{lead.phone_e164}</td>
					<td class="td font-mono text-[12px] {statusColor[lead.status] ?? 'text-muted'}">
						{#if lead.status === 'calling'}<span class="pulse-dot mr-1.5"></span>{/if}{lead.status}
					</td>
					<td class="td font-mono">{lead.attempts}</td>
					<td class="td max-w-xs truncate text-[12px] text-muted">{lead.last_error ?? ''}</td>
				</tr>
			{:else}
				<tr><td class="td text-muted" colspan="5">No leads uploaded yet.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
