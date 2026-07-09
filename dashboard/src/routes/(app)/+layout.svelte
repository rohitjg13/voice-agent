<script lang="ts">
	import { page } from '$app/state';
	import { navigating } from '$app/stores';

	let { data, children } = $props();

	const navItems = [
		{ href: '/dashboard', label: 'Overview' },
		{ href: '/agents', label: 'Agents' },
		{ href: '/packs', label: 'Packs' },
		{ href: '/campaigns', label: 'Campaigns' },
		{ href: '/calls', label: 'Calls' },
		{ href: '/appointments', label: 'Appointments' },
		{ href: '/settings/billing', label: 'Billing' }
	];

	const active = (href: string) => page.url.pathname.startsWith(href);

	let theme = $state(typeof document !== 'undefined' ? document.documentElement.getAttribute('data-theme') || 'dark' : 'dark');

	function toggleTheme() {
		const next = theme === 'dark' ? 'light' : 'dark';
		document.documentElement.setAttribute('data-theme', next);
		document.cookie = `theme=${next};path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;
		theme = next;
	}
</script>

<div class="flex min-h-screen">
	<!-- top loading bar ──────────────────────────────────────────────── -->
	<div class="nav-progress" class:nav-progress-active={Boolean($navigating)}></div>

	<aside class="flex w-56 shrink-0 flex-col bg-panel transition-colors duration-300"
		style="box-shadow: var(--shadow-sidebar);"
	>
		<div class="px-5 py-5">
			<div class="font-mono text-[10px] uppercase tracking-[0.3em] text-phos">● line open</div>
			<div class="mt-1 text-lg font-bold tracking-tight">Coldline</div>
		</div>
		<nav class="flex-1 space-y-1 px-3 py-4">
			{#each navItems as item (item.href)}
				<a
					href={item.href}
					data-sveltekit-preload-data="hover"
					class="block rounded-xl px-3 py-2 font-mono text-[13px] transition-all duration-200
						{active(item.href)
							? 'text-phos'
							: 'text-muted hover:text-ink'}"
					style={active(item.href)
						? 'box-shadow: var(--shadow-nav-active-a), var(--shadow-nav-active-b);'
						: 'box-shadow: none;'}
				>
					{active(item.href) ? '▸ ' : ''}{item.label}
				</a>
			{/each}
		</nav>
		<div class="px-3 pb-2">
			<button class="theme-toggle" onclick={toggleTheme} aria-label="Toggle theme">
				{theme === 'dark' ? '☀️' : '🌙'}
			</button>
		</div>
		<div
			class="mx-3 mb-4 rounded-xl px-5 py-4 transition-colors duration-300"
			style="box-shadow: var(--shadow-footer-a), var(--shadow-footer-b);"
		>
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
	<main class="min-w-0 flex-1 px-8 py-8 transition-colors duration-300">
		{@render children()}
	</main>
</div>

<style>
	.nav-progress {
		position: fixed;
		top: 0;
		left: 0;
		height: 2.5px;
		z-index: 9999;
		width: 0;
		background: var(--color-phos);
		border-radius: 0 1px 1px 0;
		pointer-events: none;
		transition: width 80ms ease-out;
		opacity: 0;
	}
	.nav-progress-active {
		opacity: 1;
		width: 60%;
		transition: width 4s cubic-bezier(0.1, 0.7, 0.3, 1);
	}
</style>
