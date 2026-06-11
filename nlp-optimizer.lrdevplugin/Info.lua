return {
    LrSdkVersion = 13.0,
    LrSdkMinimumVersion = 6.0,
    LrToolkitIdentifier = 'com.yourname.nlpoptimizer',
    LrPluginName = 'NLP Optimizer',

    -- Custom "Film Stock" metadata field (see FilmStockMetadata.lua)
    LrMetadataProvider = 'FilmStockMetadata.lua',

    -- Appears under File > Plug-in Extras
    LrExportMenuItems = {
        { title = 'Optimize Converted Negative(s)', file = 'OptimizeNegative.lua' },
    },
    -- Also appears in the Library menu
    LrLibraryMenuItems = {
        { title = 'Optimize Converted Negative(s)', file = 'OptimizeNegative.lua' },
    },

    VERSION = { major = 0, minor = 2, revision = 0 },
}
