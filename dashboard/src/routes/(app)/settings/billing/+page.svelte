<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();

	const sub = $derived(data.subscription);

	const meters = $derived(
		sub
			? [
					{ label: 'agents', used: sub.usage.agents, max: sub.limits.max_agents },
					{
						label: 'active campaigns',
						used: sub.usage.active_campaigns,
						max: sub.limits.max_active_campaigns
					},
					{
						label: 'call minutes',
						used: sub.usage.minutes_used,
						max: sub.limits.included_minutes
					}
				]
			: []
	);

	const price = (cents: number) => (cents === 0 ? 'Free' : `$${(cents / 100).toFixed(0)}/mo`);
</script>

<svelte:head><title>Billing — Coldline</title></svelte:head>

<h1 class="text-2xl font-bold tracking-tight">Billing</h1>
<p class="mt-1 text-sm text-muted">
	Stub checkout for now — plans and limits are real, payment isn't wired yet.
</p>

{#if form?.error}
	<p class="mt-4 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{form.error}</p>
{:else if form?.upgraded}
	<p class="mt-4 rounded-md border border-phos-dim bg-phos/10 px-3 py-2 text-sm text-phos">Plan updated.</p>
{/if}

{#if sub}
	<div class="card mt-6 p-5">
		<div class="flex items-baseline justify-between">
			<h2 class="font-semibold">
				Current plan: <span class="text-phos">{sub.plan_name}</span>
			</h2>
			<span class="font-mono text-[11px] uppercase tracking-widest text-muted">{sub.status}</span>
		</div>
		<div class="mt-4 grid gap-4 sm:grid-cols-3">
			{#each meters as m (m.label)}
				{@const pct = m.max ? Math.min(100, Math.round((m.used / m.max) * 100)) : 0}
				<div>
					<div class="flex justify-between font-mono text-[11px] uppercase tracking-widest text-muted">
						<span>{m.label}</span>
						<span class={pct >= 100 ? 'text-danger' : pct >= 80 ? 'text-amber' : ''}>
							{m.used}/{m.max}
						</span>
					</div>
					<div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line">
						<div
							class="h-full {pct >= 100 ? 'bg-danger' : pct >= 80 ? 'bg-amber' : 'bg-phos'}"
							style="width: {pct}%"
						></div>
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}

<div class="mt-6 grid gap-4 lg:grid-cols-3">
	{#each data.plans as plan (plan.id)}
		{@const current = sub?.plan_id === plan.id}
		<div class="card flex flex-col p-6 {current ? 'border-phos' : ''}">
			<div class="flex items-baseline justify-between">
				<h3 class="text-lg font-semibold">{plan.name}</h3>
				<span class="font-mono text-phos">{price(plan.price_cents)}</span>
			</div>
			<ul class="mt-4 grow space-y-2 font-mono text-[13px] text-muted">
				<li>{plan.limits.max_agents} agent{plan.limits.max_agents === 1 ? '' : 's'}</li>
				<li>{plan.limits.included_minutes} call minutes / mo</li>
				<li>{plan.limits.max_active_campaigns} active campaign{plan.limits.max_active_campaigns === 1 ? '' : 's'}</li>
				<li>{plan.limits.max_leads_per_campaign} leads / campaign</li>
			</ul>
			<form method="POST" action="?/checkout" use:enhance class="mt-5">
				<input type="hidden" name="plan_id" value={plan.id} />
				<button class="{current ? 'btn-ghost' : 'btn'} w-full justify-center" type="submit" disabled={current}>
					{current ? 'Current plan' : plan.price_cents === 0 ? 'Switch to free' : 'Upgrade'}
				</button>
			</form>
		</div>
	{/each}
</div>
