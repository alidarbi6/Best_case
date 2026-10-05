-- Time log with well name, job type and wellbore description (specification v2).
-- Date / time columns are extracted afterwards in Python.
SELECT
  r."idwell",
  r."idrecparent",
  r."idrec",
  r."dttmend",
  r."dttmstart",
  r."plannextrptops",
  r."rpttmactops",
  r."summaryops",
  t."code1",
  t."code2",
  t."code3",
  t."code4",
  t."com",
  t."duration",
  t."idrecwellbore",
  t."opscategory",
  t."sysseq",
  wh."wellname",
  j."jobtyp",
  wb."des"
FROM dbo.wvt_wvjobreport r
LEFT JOIN dbo.wvt_wvjobreporttimelog t
  ON r."idwell" = t."idwell"
 AND r."idrec" = t."idrecparent"
LEFT JOIN dbo.wvt_wvjob j
  ON r."idwell" = j."idwell"
 AND r."idrecparent" = j."idrec"
LEFT JOIN dbo.wvt_wvwellheader wh
  ON j."idwell" = wh."idwell"
LEFT JOIN dbo.wvt_wvjobrig rig
  ON j."idrec" = rig."idrecparent"
LEFT JOIN dbo.wvt_wvwellbore wb
  ON r."idwell" = wb."idwell"
 AND t."idrecwellbore" = wb."idrec";
