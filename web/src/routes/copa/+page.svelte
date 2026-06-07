<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type CopaGroup, type CopaStanding } from '$lib/supabase';

	let groups = $state<CopaGroup[]>([]);
	let standings = $state<CopaStanding[]>([]);
	let selJornada = $state<number | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const { data: g, error: eg } = await supabase.from('copa_groups').select('*');
			if (eg) throw eg;
			const { data: s, error: es } = await supabase
				.from('copa_standings')
				.select('*')
				.order('posicio');
			if (es) throw es;
			groups = (g ?? []) as CopaGroup[];
			standings = (s ?? []) as CopaStanding[];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const phases = $derived.by(() => {
		const m = new Map<number, { nom: string; ordre: number }>();
		for (const g of groups)
			if (!m.has(g.jornada))
				m.set(g.jornada, { nom: g.jornada_nom ?? `Fase ${g.jornada}`, ordre: g.ordre ?? g.jornada });
		return [...m.entries()]
			.map(([jornada, v]) => ({ jornada, ...v }))
			.sort((a, b) => a.ordre - b.ordre);
	});

	$effect(() => {
		if (selJornada == null && phases.length) selJornada = phases[0].jornada;
	});

	const phaseGroups = $derived(
		groups
			.filter((g) => g.jornada === selJornada)
			.sort((a, b) => (a.grup_nom ?? '').localeCompare(b.grup_nom ?? ''))
	);

	function rows(gid: number): CopaStanding[] {
		return standings
			.filter((s) => s.jornada === selJornada && s.grup_id === gid)
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}

	let collapsed = $state(new Set<number>());
	function toggle(id: number) {
		const s = new Set(collapsed);
		s.has(id) ? s.delete(id) : s.add(id);
		collapsed = s;
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if phases.length === 0}
	<p class="py-6 text-center text-sm text-slate-400">Sense classificacions de copa.</p>
{:else}
	<!-- Fases: xips -->
	<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each phases as f}
			<button
				onclick={() => (selJornada = f.jornada)}
				class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {f.jornada === selJornada
					? 'bg-slate-900 text-white'
					: 'bg-white text-slate-600 ring-1 ring-slate-200'}">{f.nom}</button>
		{/each}
	</div>

	{#each phaseGroups as g (g.grup_id)}
		<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<button
				onclick={() => toggle(g.grup_id)}
				class="flex w-full items-center gap-2 bg-slate-50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500"
			>
				<span class="flex-1">{g.grup_nom ?? 'Grup'}</span>
				<span class="font-normal normal-case text-slate-400">{rows(g.grup_id).length} equips</span>
				<span class="text-slate-400 transition-transform {collapsed.has(g.grup_id) ? '' : 'rotate-90'}">›</span>
			</button>
			{#if !collapsed.has(g.grup_id)}
			<div class="flex items-center gap-2 border-y border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-5 text-center">#</span>
				<span class="flex-1">Equip</span>
				<span class="w-12 text-right">Mitj.</span>
				<span class="w-9 text-right">Pts</span>
			</div>
			<ul>
				{#each rows(g.grup_id) as r (r.equip)}
					<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
						<span
							class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1
								? 'text-amber-500'
								: 'text-slate-400'}">{r.posicio}</span>
						<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{r.equip}</div>
						<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-400">
							{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}
						</span>
						<span class="w-9 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
					</li>
				{/each}
			</ul>
			{/if}
		</section>
	{/each}
{/if}
