<script lang="ts">
	import { page } from '$app/state';

	let { data, children } = $props();

	const nav = [
		{ href: '/dashboard', label: 'Overview' },
		{ href: '/agents', label: 'Agents' },
		{ href: '/campaigns', label: 'Campaigns' },
		{ href: '/calls', label: 'Calls' },
		{ href: '/appointments', label: 'Appointments' },
		{ href: '/settings/billing', label: 'Billing' }
	];

	const active = (href: string) => page.url.pathname.startsWith(href);
</script>

<div class="flex min-h-screen">
	<aside class="flex w-56 shrink-0 flex-col border-r border-line bg-panel/60">
		<div class="border-b border-line px-5 py-5">
			<div class="font-mono text-[10px] uppercase tracking-[0.3em] text-phos">● line open</div>
			<div class="mt-1 text-lg font-bold tracking-tight">Coldline</div>
		</div>
		<nav class="flex-1 space-y-0.5 px-3 py-4">
			{#each nav as item (item.href)}
				<a
					href={item.href}
					class="block rounded-md px-3 py-2 font-mono text-[13px] transition
						{active(item.href) ? 'bg-phos/10 text-phos' : 'text-muted hover:bg-panel2 hover:text-ink'}"
				>
					{active(item.href) ? '▸ ' : ''}{item.label}
				</a>
			{/each}
		</nav>
		<div class="border-t border-line px-5 py-4">
			<div class="truncate text-sm font-semibold">{data.me.org?.name}</div>
			<div class="mt-0.5 flex items-center justify-between">
				<span class="font-mono text-[10px] uppercase tracking-widest text-amber">
					{data.me.subscription?.plan_name ?? 'no plan'}
				</span>
				<form method="POST" action="/logout">
					<button class="cursor-pointer font-mono text-[11px] text-muted hover:text-danger" type="submit">
						sign out
					</button>
				</form>
			</div>
		</div>
	</aside>
	<main class="min-w-0 flex-1 px-8 py-8">
		{@render children()}
	</main>
</div>
