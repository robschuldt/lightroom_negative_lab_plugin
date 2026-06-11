--[[
  OptimizeNegative.lua

  For each selected photo:
    1. Export a small sRGB JPEG of the NLP-converted positive to a temp folder.
    2. POST its path to the local Python server, which returns adjustment deltas.
    3. Read the photo's current develop settings, add the deltas (clamped), and
       apply them on top of the existing NLP conversion.

  The negative itself and NLP's own controls are never touched — this is a
  polish layer that stacks on standard Lightroom sliders.
]]

local LrApplication     = import 'LrApplication'
local LrTasks           = import 'LrTasks'
local LrFunctionContext = import 'LrFunctionContext'
local LrExportSession   = import 'LrExportSession'
local LrPathUtils       = import 'LrPathUtils'
local LrFileUtils       = import 'LrFileUtils'
local LrHttp            = import 'LrHttp'
local LrDialogs         = import 'LrDialogs'
local LrView            = import 'LrView'
local LrBinding         = import 'LrBinding'

local SERVER_URL = 'http://127.0.0.1:8765/analyze'

-- Popup choices for the film-stock dialog. Values must match film_profiles.py
-- (and FilmStockMetadata.lua).
local FILM_STOCK_ITEMS = {
    { title = 'Generic color negative',        value = 'generic_color' },
    { title = 'Kodak Portra 160',              value = 'kodak_portra_160' },
    { title = 'Kodak Portra 400',              value = 'kodak_portra_400' },
    { title = 'Kodak Portra 800',              value = 'kodak_portra_800' },
    { title = 'Kodak Ektar 100',               value = 'kodak_ektar_100' },
    { title = 'Kodak Gold 200',                value = 'kodak_gold_200' },
    { title = 'Kodak UltraMax 400',            value = 'kodak_ultramax_400' },
    { title = 'Fuji Pro 400H',                 value = 'fuji_pro_400h' },
    { title = 'Fuji Superia 400',              value = 'fuji_superia_400' },
    { title = 'Fuji C200',                     value = 'fuji_c200' },
    { title = 'CineStill 800T',                value = 'cinestill_800t' },
    { title = 'CineStill 50D',                 value = 'cinestill_50d' },
    { title = 'Slide / E-6 (Velvia, Provia)',  value = 'slide_e6' },
    { title = 'Black & white (generic)',       value = 'bw_generic' },
    { title = 'Ilford HP5 Plus 400',           value = 'ilford_hp5_400' },
    { title = 'Kodak Tri-X 400',               value = 'kodak_trix_400' },
    { title = 'Kodak T-Max 100',               value = 'kodak_tmax_100' },
}

-- Read a photo's tagged film stock, or nil if not set.
-- 'other' resolves to the free-text custom name the user typed.
local function getFilmStock(photo)
    local v = photo:getPropertyForPlugin(_PLUGIN, 'filmStock')
    if v == 'other' then
        local c = photo:getPropertyForPlugin(_PLUGIN, 'filmStockCustom')
        if c ~= nil and c ~= '' then return c end
        return nil
    end
    if v == nil or v == '' then return nil end
    return v
end

-- Ask the user to pick one stock for this run (used when frames aren't tagged).
-- Returns (enumValue, customName); customName is non-nil when an obscure stock
-- was typed, in which case it is looked up by the server.
local function chooseFilmStock(context)
    local props = LrBinding.makePropertyTable(context)
    props.stock = 'generic_color'
    props.custom = ''
    local f = LrView.osFactory()
    local contents = f:column{
        spacing = f:control_spacing(),
        f:static_text{ title = 'Some selected photos have no film stock tagged.' },
        f:row{
            f:static_text{ title = 'Pick a stock:' },
            f:popup_menu{
                value = LrView.bind{ key = 'stock', object = props },
                items = FILM_STOCK_ITEMS,
                width = 240,
            },
        },
        f:static_text{ title = '...or type an obscure stock to look up:' },
        f:edit_field{
            value = LrView.bind{ key = 'custom', object = props },
            width_in_chars = 30,
            immediate = true,
        },
    }
    local result = LrDialogs.presentModalDialog{
        title = 'NLP Optimizer - Film Stock',
        contents = contents,
    }
    if result ~= 'ok' then return nil, nil end
    local custom = props.custom
    if custom then custom = custom:gsub('^%s+', ''):gsub('%s+$', '') end
    if custom == '' then custom = nil end
    return props.stock, custom
end

local function clamp(v, lo, hi)
    if v < lo then return lo elseif v > hi then return hi else return v end
end

-- Parse the server's "Key=Value" body (lines starting with # are ignored).
local function parseResponse(body)
    local t = {}
    for line in body:gmatch('[^\r\n]+') do
        if line:sub(1, 1) ~= '#' then
            local k, v = line:match('^(%w+)=(.+)$')
            if k and v then t[k] = tonumber(v) end
        end
    end
    return t
end

-- Export a small JPEG of the current rendered (converted) state.
local function exportPreview(photo)
    local tempDir = LrPathUtils.getStandardFilePath('temp')
    local session = LrExportSession({
        photosToExport = { photo },
        exportSettings = {
            LR_export_destinationType      = 'specificFolder',
            LR_export_destinationPathPrefix = tempDir,
            LR_export_useSubfolder         = false,
            LR_collisionHandling           = 'overwrite',
            LR_format                      = 'JPEG',
            LR_jpeg_quality                = 0.9,
            LR_export_colorSpace           = 'sRGB',
            LR_size_doConstrain            = true,
            LR_size_maxWidth               = 2000,
            LR_size_maxHeight              = 2000,
            LR_size_doNotEnlarge           = true,
            LR_minimizeEmbeddedMetadata    = true,
        },
    })
    local exportedPath
    for _, rendition in session:renditions() do
        local ok, pathOrMsg = rendition:waitForRender()
        if ok then exportedPath = pathOrMsg end
    end
    return exportedPath
end

local function optimizePhoto(photo, filmStock)
    local exportedPath = exportPreview(photo)
    if not exportedPath then return false, 'export failed' end

    local requestBody = 'film=' .. (filmStock or 'generic_color') ..
                        '\npath=' .. exportedPath
    local body = LrHttp.post(SERVER_URL, requestBody,
        { { field = 'Content-Type', value = 'text/plain' } })

    LrFileUtils.delete(exportedPath)

    if not body or body:match('^#%s*error') then
        return false, 'server error or not running'
    end

    local adj = parseResponse(body)

    -- Is this a raw file? Temperature/Tint units differ for raw vs rendered.
    local fmt   = photo:getRawMetadata('fileFormat')
    local isRaw = (fmt == 'RAW' or fmt == 'DNG')

    local cur = photo:getDevelopSettings()
    local function curv(key, default)
        local x = cur[key]
        if x == nil then return default else return x end
    end

    local ns = {}
    ns.Exposure2012   = clamp(curv('Exposure2012', 0)   + (adj.ExposureDelta   or 0), -5,   5)
    ns.Contrast2012   = clamp(curv('Contrast2012', 0)   + (adj.ContrastDelta   or 0), -100, 100)
    ns.Highlights2012 = clamp(curv('Highlights2012', 0) + (adj.HighlightsDelta or 0), -100, 100)
    ns.Shadows2012    = clamp(curv('Shadows2012', 0)    + (adj.ShadowsDelta    or 0), -100, 100)
    ns.Whites2012     = clamp(curv('Whites2012', 0)     + (adj.WhitesDelta     or 0), -100, 100)
    ns.Blacks2012     = clamp(curv('Blacks2012', 0)     + (adj.BlacksDelta     or 0), -100, 100)
    ns.Vibrance       = clamp(curv('Vibrance', 0)       + (adj.VibranceDelta   or 0), -100, 100)

    local tShift  = adj.TempShiftNorm or 0
    local tiShift = adj.TintShiftNorm or 0
    if isRaw then
        ns.Temperature = clamp(curv('Temperature', 5000) + tShift  * 500, 2000, 50000)
        ns.Tint        = clamp(curv('Tint', 0)           + tiShift * 15,  -150, 150)
    else
        ns.Temperature = clamp(curv('Temperature', 0) + tShift  * 20, -100, 100)
        ns.Tint        = clamp(curv('Tint', 0)        + tiShift * 15, -100, 100)
    end

    local catalog = LrApplication.activeCatalog()
    catalog:withWriteAccessDo('NLP Optimize', function()
        photo:applyDevelopSettings(ns)
    end)

    return true
end

LrFunctionContext.callWithContext('nlpOptimize', function()
    LrTasks.startAsyncTask(function()
        local catalog = LrApplication.activeCatalog()
        local photos  = catalog:getTargetPhotos()
        if #photos == 0 then
            LrDialogs.message('NLP Optimizer', 'Select at least one photo first.')
            return
        end

        -- If any selected frame has no film stock tagged, ask once and apply
        -- that choice to the untagged frames (so it sticks for next time).
        local anyUnset = false
        for _, photo in ipairs(photos) do
            if not getFilmStock(photo) then anyUnset = true; break end
        end

        local chosenEnum, chosenCustom = nil, nil
        if anyUnset then
            LrFunctionContext.callWithContext('nlpChooseFilm', function(ctx)
                chosenEnum, chosenCustom = chooseFilmStock(ctx)
            end)
            if not chosenEnum and not chosenCustom then return end   -- user cancelled
            catalog:withWriteAccessDo('Set Film Stock', function()
                for _, photo in ipairs(photos) do
                    if not getFilmStock(photo) then
                        if chosenCustom then
                            photo:setPropertyForPlugin(_PLUGIN, 'filmStock', 'other')
                            photo:setPropertyForPlugin(_PLUGIN, 'filmStockCustom', chosenCustom)
                        else
                            photo:setPropertyForPlugin(_PLUGIN, 'filmStock', chosenEnum)
                        end
                    end
                end
            end)
        end

        local fallback = chosenCustom or chosenEnum or 'generic_color'
        local done, failed, lastError = 0, 0, nil
        for _, photo in ipairs(photos) do
            local stock = getFilmStock(photo) or fallback
            local ok, err = optimizePhoto(photo, stock)
            if ok then done = done + 1 else failed = failed + 1; lastError = err end
        end

        local msg = done .. ' optimized, ' .. failed .. ' failed.'
        if lastError then msg = msg .. '\n\nLast error: ' .. lastError end
        LrDialogs.message('NLP Optimizer', msg)
    end)
end)
