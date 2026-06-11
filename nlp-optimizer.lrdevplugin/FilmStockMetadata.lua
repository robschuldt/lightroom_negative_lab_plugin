--[[
  FilmStockMetadata.lua

  Defines a custom "Film Stock" field stored per-photo in the catalog. Tag a roll
  once and sync it across the frames; the optimizer reads this to pick a profile.
  The values here must match the keys in the Python film_profiles.py.
]]

return {
    metadataFieldsForPhotos = {
        {
            id = 'filmStock',
            title = 'Film Stock',
            dataType = 'enum',
            version = 1,
            searchable = true,
            browsable = true,
            allowPluginToSetOnImport = true,
            values = {
                { value = '',                   title = '(not set)' },
                { value = 'generic_color',       title = 'Generic color negative' },
                { value = 'kodak_portra_160',    title = 'Kodak Portra 160' },
                { value = 'kodak_portra_400',    title = 'Kodak Portra 400' },
                { value = 'kodak_portra_800',    title = 'Kodak Portra 800' },
                { value = 'kodak_ektar_100',     title = 'Kodak Ektar 100' },
                { value = 'kodak_gold_200',      title = 'Kodak Gold 200' },
                { value = 'kodak_ultramax_400',  title = 'Kodak UltraMax 400' },
                { value = 'fuji_pro_400h',       title = 'Fuji Pro 400H' },
                { value = 'fuji_superia_400',    title = 'Fuji Superia 400' },
                { value = 'fuji_c200',           title = 'Fuji C200' },
                { value = 'cinestill_800t',      title = 'CineStill 800T' },
                { value = 'cinestill_50d',       title = 'CineStill 50D' },
                { value = 'slide_e6',            title = 'Slide / E-6 (Velvia, Provia)' },
                { value = 'bw_generic',          title = 'Black & white (generic)' },
                { value = 'ilford_hp5_400',      title = 'Ilford HP5 Plus 400' },
                { value = 'kodak_trix_400',      title = 'Kodak Tri-X 400' },
                { value = 'kodak_tmax_100',      title = 'Kodak T-Max 100' },
                { value = 'other',               title = 'Other / obscure (typed)' },
            },
        },
        {
            id = 'filmStockCustom',
            title = 'Film Stock (custom name)',
            dataType = 'string',
            version = 1,
            searchable = true,
            browsable = true,
        },
    },
    schemaVersion = 2,
}
