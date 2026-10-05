-- Drill string + components + drilling parameters + well name / job type (specification v2)
SELECT
  ds."idwell",
  ds."idrecparent",
  ds."idrec",
  ds."bitno",
  ds."bittfa",
  ds."com",
  ds."des",
  ds."stringno",
  ds."wearbearing",
  ds."weardull",
  ds."weargauge",
  ds."wearinner",
  ds."wearloc",
  ds."wearother",
  ds."wearouter",
  ds."wearpulled",
  dsc."com" AS "com_DrillstringComp",
  dsc."des" AS "des_DrillstringComp",
  dsc."grade",
  dsc."hoursstart",
  dsc."joints",
  dsc."length",
  dsc."make",
  dsc."model",
  dsc."sysseq",
  dp."depthend",
  dp."depthstart",
  dp."dttmend",
  dp."dttmstart",
  dp."hookloadoffbottom",
  dp."hookloadpickup",
  dp."hookloadrotating",
  dp."hookloadslackoff",
  dp."idrecwellbore",
  dp."liquidinjrate",
  dp."rpmmotor",
  dp."rpmstring",
  dp."sppdiff",
  dp."sppdrill",
  dp."tfo",
  dp."tmcirc",
  dp."tmdrill",
  dp."torquedrill",
  dp."torqueoffbtm",
  dp."wob",
  wh."wellname",
  j."jobtyp"
FROM dbo.wvt_wvjobdrillstring ds
LEFT JOIN dbo.wvt_wvjobdrillstringcomp dsc
  ON ds."idwell" = dsc."idwell"
 AND ds."idrec" = dsc."idrecparent"
LEFT JOIN dbo.wvt_wvjobdrillstringdrillparam dp
  ON ds."idwell" = dp."idwell"
 AND ds."idrec" = dp."idrecparent"
LEFT JOIN dbo.wvt_wvwellheader wh
  ON dp."idwell" = wh."idwell"
LEFT JOIN dbo.wvt_wvjob j
  ON wh."idwell" = j."idwell"
LEFT JOIN dbo.wvt_wvjobrig rig
  ON j."idrec" = rig."idrecparent";
