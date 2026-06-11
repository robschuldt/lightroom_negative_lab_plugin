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

local SERVER_URL = 'http://127.0.0.1:8765/analyze'

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

local function optimizePhoto(photo)
    local exportedPath = exportPreview(photo)
    if not exportedPath then return false, 'export failed' end

    local body = LrHttp.post(SERVER_URL, exportedPath,
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

        local done, failed, lastError = 0, 0, nil
        for _, photo in ipairs(photos) do
            local ok, err = optimizePhoto(photo)
            if ok then done = done + 1 else failed = failed + 1; lastError = err end
        end

        local msg = done .. ' optimized, ' .. failed .. ' failed.'
        if lastError then msg = msg .. '\n\nLast error: ' .. lastError end
        LrDialogs.message('NLP Optimizer', msg)
    end)
end)
