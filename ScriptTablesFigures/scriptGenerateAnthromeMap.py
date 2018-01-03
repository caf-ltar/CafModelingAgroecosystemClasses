import arcpy
from arcpy import env
from arcpy.sa import *
import os.path

# --- PARAMS AND SETUP ---------------------------------------------------------
# Parameters
_irrigatedPath = os.path.join("Working","CDL_2016_Irrigated_AlgorithmicIrrigated.tif")
_workingDirName = "WorkingTemp"
_resultDirName = "Results"
tempFolderName = "temp"
shouldSaveIntermediateLayers = False

# Environment Parameters
arcpy.env.workspace = r"C:\OneDrive - Washington State University (email.wsu.edu)\Projects\CafModelingAgroecosystemClasses\2017\Methods\GIS"
arcpy.env.overwriteOutput = True
arcpy.env.snapRaster = arcpy.env.workspace + os.path.sep + _irrigatedPath
tempFolder = arcpy.env.workspace + os.path.sep + tempFolderName
arcpy.CreateFolder_management(arcpy.env.workspace, tempFolderName)
arcpy.env.scratchWorkspace = tempFolder
#tmpFC = arcpy.CreateScratchNames(...., "in_memory") #from: https://geonet.esri.com/thread/89289

_coordinateSystem = arcpy.SpatialReference("WGS 1984 UTM Zone 11N")
years = [
    2016,
    2015,
    2014,
    2013,
    2012,
    2011,
    2010,
    2009,
    2008,
    2007]
# //- PARAMS AND SETUP ---------------------------------------------------------

def createAnthromeMap(
    dirPathToAndersonLayers, 
    irrigatedPath, 
    outputDirWorking, 
    outputDirPathResult,
    coordinateSystem,
    shouldSaveIntermediateLayers = False):
    """ 
    This function is largely a copy/paste from "scriptGenerateAec.py" with changes
    so that dryland ag pixels are not split between aec classes.  The similarly
    named function in "scriptGenerateAec.py" is a misnomer and should be named
    "createAecMap" as this function creates the true "anthrome" map.

    Parameters
    ----------
    dirPathToAndersonLayers : string
        Path to directory that contains geotif files with Anderson
        classifications - these are generated by running "scriptGenerateAec.py"
    irrigatedPath : string
        Path to master irrigation layer.  This is created outside of any scripts
        so see methods for details.  Irrigated crop pixels as indicated in this
        layer are consistant across all years
    outputDirWorking : string
        Path to directory where working files should be saved
    outputDirPathResult : string
        Path to directory where result files should be saved
    coordinateSystem : arcpy.SpatialReference
        Usually "WGS 1984 UTM Zone 11N"
    shouldSaveIntermediateLayers : bool
        If true, intermediate, working, files will be saved in outputDirWorking
    """

    print("Creating anthrome map...")
    anthromes = []

    for year in years:
        
        print("... processing ag layer")
        
        # Combine Ag layers and relcass
        drylandAg = Raster(os.path.join(
            dirPathToAndersonLayers, "CDL_"+str(year)+"_AgNoIrrigated.tif"))
        irrigated = Raster(irrigatedPath)
        orchard = Raster(os.path.join(
            dirPathToAndersonLayers, "CDL_"+str(year)+ "_Orchard.tif"))
        agriculture = SetNull(IsNull(drylandAg) & IsNull(irrigated) & IsNull(orchard),50)
        agriculture.save(
            os.path.join(
                outputDirWorking, "agriculture_"+str(year)+".tif"))

        print("... processing water and other layer")
        # Combine layers into "Water and Others" and reclass
        water = Raster(os.path.join(
            dirPathToAndersonLayers, "CDL_"+str(year)+ "_Water.tif"))
        wetland = Raster(os.path.join(
            dirPathToAndersonLayers, "CDL_"+str(year)+ "_Wetland.tif"))  
        barren = Raster(os.path.join(
            dirPathToAndersonLayers, "CDL_"+str(year)+ "_Barren.tif"))
        wilderness = Raster(os.path.join(
            dirPathToAndersonLayers, "CDL_"+str(year)+ "_Wilderness.tif"))
        #Con((rasterIn == 87) | (rasterIn == 190) | (rasterIn == 195),6)
        #rasterDrylandFallow = Con((rasterDryland == 61),1,0)
        #rasterAnnual = Con((rasterFocalStatistic <= 0.1)&(rasterAgNoIrrigated==1),11)
        waterAndOther = SetNull(IsNull(water) & IsNull(wetland) & IsNull(barren) & IsNull(wilderness),51)
        waterAndOther.save(
            os.path.join(
                outputDirWorking, "waterOther_"+str(year)+".tif"))

        print("... stitching year " + str(year))
        andersonLayers = [
            agriculture,
            Raster(os.path.join(
                dirPathToAndersonLayers, "CDL_"+str(year)+ "_Forest.tif")),
            waterAndOther,
            Raster(os.path.join(
                dirPathToAndersonLayers, "CDL_"+str(year)+ "_Urban.tif")),
            Raster(os.path.join(
                dirPathToAndersonLayers, "CDL_"+str(year)+ "_Range.tif")),
        ]

        anthromes.append(
            arcpy.MosaicToNewRaster_management(
                andersonLayers,
                outputDirWorking,
                "anthrome"+str(year)+".tif",
                coordinateSystem,"8_BIT_UNSIGNED",30,1,"FIRST","FIRST")
        )
    
    print("Running cell statistics...")
    majorityRasterTempPath = os.path.join(
        outputDirWorking, "anthromeMajorityRasterTemp.tif")
    majorityPath = os.path.join(
        outputDirWorking, "anthromeMajorityRaster.tif")
    
    # Create MAJORITY Cell Statistic layer
    print("... calculating majorities")
    majorityRasterTemp = arcpy.gp.CellStatistics_sa(anthromes, 
        majorityRasterTempPath,
        "MAJORITY", "DATA")
    
    # Returns largest YYYY in list of anthromeYYYY.tif
    anthromePathCurrYear = os.path.join(
        outputDirWorking, 
        "anthrome" + str(sorted(years, reverse=True)[0]) + ".tif")

    # The MAJORITY function in Cell Statistics returns NoData if a tie for majority, so fill these with current year's value'
    majorityRaster = Con(
        IsNull(majorityRasterTempPath), 
        anthromePathCurrYear, 
        majorityRasterTempPath)
    majorityRaster.save(majorityPath)
    
    print("... calculating varieties")
    varietyRaster = arcpy.gp.CellStatistics_sa(anthromes, 
        os.path.join(outputDirWorking, "anthromeVarietyRaster.tif"),
        "VARIETY", "DATA")
    
    
    varietyPath = os.path.join(outputDirWorking, "anthromeVarietyRaster.tif")

    # Get cutoff value, should be greater than 50%
    dynamicUnstableCuttoff = int((len(anthromes)/2) + 0.5)

    print("Generating stable, dynamic, and unstable rasters...")
    stableAnthromeRaster = Con(varietyPath, majorityPath, "", "Value = 1")
    dynamicAnthromeRaster = Con(
        varietyPath, 
        Raster(majorityPath) + 100, 
        "", "Value > 1 AND Value <= " + str(dynamicUnstableCuttoff))
    unstableAnthromeRaster = Con(
        varietyPath, 
        Raster(majorityPath) + 200, "", "Value > " + str(dynamicUnstableCuttoff))

    stableAnthromeRaster.save(
        os.path.join(outputDirPathResult, "anthromeStable.tif"))
    dynamicAnthromeRaster.save(
        os.path.join(outputDirPathResult, "anthromeDynamic.tif"))
    unstableAnthromeRaster.save(
        os.path.join(outputDirPathResult, "anthromeUnstable.tif"))

    print("Compressing rasters...")
    arcpy.MosaicToNewRaster_management(
        [stableAnthromeRaster, dynamicAnthromeRaster, unstableAnthromeRaster],
        outputDirPathResult,"anthrome.tif",
        arcpy.SpatialReference("WGS 1984 UTM Zone 11N"),
        "8_BIT_UNSIGNED",30,1,"FIRST","FIRST")

    print("Cleaning up...")
    # Cleanup
    if(shouldSaveIntermediateLayers == False):
        #arcpy.Delete_management(stableRaster)
        #arcpy.Delete_management(dynamicRaster)
        arcpy.Delete_management(majorityRaster)
        arcpy.Delete_management(majorityRasterTemp)
        arcpy.Delete_management(varietyRaster)

# Main ----
arcpy.CheckOutExtension("spatial")

createAnthromeMap(
    os.path.join(arcpy.env.workspace, _workingDirName), 
    os.path.join(arcpy.env.workspace, _irrigatedPath), 
    os.path.join(arcpy.env.workspace, _workingDirName, "anthromeProper"), 
    os.path.join(arcpy.env.workspace, _resultDirName, "anthromeProper"),
    _coordinateSystem,
    shouldSaveIntermediateLayers)

arcpy.CheckInExtension("spatial")

# Cleanup
arcpy.Delete_management(tempFolder)

print("DONE")