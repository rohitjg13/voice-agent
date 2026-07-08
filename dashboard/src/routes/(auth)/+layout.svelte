<script lang="ts">
	let { children } = $props();
</script>

<div class="flex min-h-screen items-center justify-center px-4">
	<div class="w-full max-w-sm">
		<div class="mb-8 text-center">
			<div class="font-mono text-[11px] uppercase tracking-[0.3em] text-phos">
				● line open
			</div>
			<h1 class="mt-2 text-3xl font-bold tracking-tight">Coldline</h1>
			<p class="mt-1 text-sm text-muted">AI cold-calling, on your numbers.</p>
		</div>
		{@render children()}
	</div>
</div>
