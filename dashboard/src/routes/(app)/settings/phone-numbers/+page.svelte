<script lang="ts">
	import { enhance } from '$app/forms';

	let { data, form } = $props();
</script>

<svelte:head><title>Phone numbers — Coldline</title></svelte:head>

<h1 class="text-2xl font-bold tracking-tight">Phone numbers</h1>
<p class="mt-1 text-sm text-muted">Outbound caller IDs provisioned through Vapi.</p>

{#if form?.error}
	<p class="mt-4 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{form.error}</p>
{:else if form?.bought}
	<p class="mt-4 rounded-md border border-phos-dim bg-phos/10 px-3 py-2 text-sm text-phos">Number provisioned.</p>
{/if}

<form method="POST" action="?/buy" use:enhance class="card mt-6 flex items-end gap-4 p-5">
	<div>
		<label class="label" for="area_code">Area code (optional)</label>
		<input class="input w-32 font-mono" id="area_code" name="area_code" pattern="[0-9]{3}" placeholder="312" />
	</div>
	<button class="btn" type="submit">Provision number</button>
</form>

<div class="card mt-6 overflow-x-auto">
	<table class="w-full">
		<thead>
			<tr><th class="th">Number</th><th class="th">Status</th><th class="th">Added</th></tr>
		</thead>
		<tbody>
			{#each data.numbers as n (n.id)}
				<tr class="hover:bg-panel2">
					<td class="td font-mono">{n.e164}</td>
					<td class="td font-mono text-[12px] text-phos">{n.status}</td>
					<td class="td text-muted">{n.created_at ? new Date(n.created_at).toLocaleDateString() : '—'}</td>
				</tr>
			{:else}
				<tr><td class="td text-muted" colspan="3">No numbers yet.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
