<script lang="ts">
	let { data } = $props();

	const c = $derived(data.call);

	const meta = $derived([
		['outcome', c.outcome ?? '—'],
		['stage reached', c.stage_reached ?? '—'],
		['ended reason', c.ended_reason ?? '—'],
		['duration', c.duration_seconds != null ? `${c.duration_seconds}s` : '—'],
		['cost', c.cost_usd != null ? `$${Number(c.cost_usd).toFixed(3)}` : '—'],
		['objections', c.objections.length ? c.objections.join(', ') : 'none']
	]);
</script>

<svelte:head><title>Call {c.customer_number ?? ''} — Coldline</title></svelte:head>

<a class="font-mono text-[12px] text-muted hover:text-phos" href="/calls">← call log</a>
<div class="mt-1 flex items-baseline gap-4">
	<h1 class="text-2xl font-bold tracking-tight">{c.customer_number ?? 'Unknown number'}</h1>
	{#if c.booked}<span class="font-mono text-[12px] uppercase tracking-widest text-phos">● booked</span>{/if}
</div>
<p class="mt-1 text-sm text-muted">{c.created_at ? new Date(c.created_at).toLocaleString() : ''}</p>

<div class="mt-6 grid gap-6 lg:grid-cols-3">
	<div class="card h-fit p-5">
		<h2 class="mb-4 font-semibold">Details</h2>
		<dl class="space-y-3">
			{#each meta as [k, v] (k)}
				<div class="flex justify-between gap-4 text-sm">
					<dt class="font-mono text-[11px] uppercase tracking-widest text-muted">{k}</dt>
					<dd class="text-right font-mono text-[13px]">{v}</dd>
				</div>
			{/each}
		</dl>
		{#if c.summary}
			<h2 class="mt-6 mb-2 font-semibold">Summary</h2>
			<p class="text-sm text-muted">{c.summary}</p>
		{/if}
	</div>

	<div class="card p-5 lg:col-span-2">
		<h2 class="mb-4 font-semibold">Transcript</h2>
		{#if !c.transcript?.length}
			<p class="text-sm text-muted">No transcript recorded.</p>
		{:else}
			<div class="space-y-3">
				{#each c.transcript as turn, i (i)}
					<div class="flex gap-3 {turn.role === 'assistant' ? '' : 'flex-row-reverse'}">
						<span class="mt-1 shrink-0 font-mono text-[10px] uppercase tracking-widest
							{turn.role === 'assistant' ? 'text-phos' : 'text-amber'}">
							{turn.role === 'assistant' ? 'agent' : 'prospect'}
						</span>
						<p class="max-w-[85%] rounded-lg border px-3 py-2 text-sm
							{turn.role === 'assistant' ? 'border-phos-dim/40 bg-phos/5' : 'border-line bg-panel2'}">
							{turn.content}
						</p>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
