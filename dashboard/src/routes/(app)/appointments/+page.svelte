<script lang="ts">
	let { data } = $props();
</script>

<svelte:head><title>Appointments — Coldline</title></svelte:head>

<h1 class="text-2xl font-bold tracking-tight">Appointments</h1>
<p class="mt-1 text-sm text-muted">Demos and meetings your agents booked.</p>

<div class="card mt-6 overflow-x-auto">
	<table class="w-full">
		<thead>
			<tr>
				<th class="th">Prospect</th><th class="th">Email</th><th class="th">Requested time</th>
				<th class="th">Booked</th><th class="th">When</th>
			</tr>
		</thead>
		<tbody>
			{#each data.appointments as a (a.id)}
				<tr class="row-hover">
					<td class="td">{a.prospect_name ?? '—'}</td>
					<td class="td font-mono text-[13px]">{a.prospect_email ?? '—'}</td>
					<td class="td">{a.requested_time ?? '—'}</td>
					<td class="td font-mono text-[12px] {a.booked ? 'text-phos' : 'text-muted'}">
						{a.booked ? '● yes' : 'no'}
					</td>
					<td class="td whitespace-nowrap text-muted">{a.created_at ? new Date(a.created_at).toLocaleString() : '—'}</td>
				</tr>
			{:else}
				<tr><td class="td text-muted" colspan="5">Nothing booked yet.</td></tr>
			{/each}
		</tbody>
	</table>
</div>
