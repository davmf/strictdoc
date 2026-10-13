package HalcyonAllocation {
    doc /*
     * Configuration of the analyser (ISA-88 process cell). The abstract
     * Instrument owns the physical units, the sample procedure and every
     * allocation of a step to equipment. Concrete configurations (scenarios
     * package) set the capacity of each unit.
     *
     * An allocation seizes the unit for the duration of the step. A step
     * with several allocations seizes all of them. An allocation to a
     * Store draws the step's consumes amount when the step starts.
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SimLib::*;
    private import HalcyonHardware::*;
    private import HalcyonWorkflow::*;

    abstract part def <'AL-INS'> Instrument :> Configuration {
        part rack : SampleRack;
        part shuttle : Shuttle;
        part gantry : PipettingGantry;
        part stations : ExtractionStation;
        part pneumatics : PneumaticController;
        part generators : DropletGenerator;
        part blocks : ThermalBlock;
        part imagers : FluorescenceImager;
        part reagentStore : ReagentStore;
        part wasteStore : WasteStore;
        part cartridge : Cartridge;
        attribute :>> maxRetests = 1;

        perform action sampleProcedure : SampleProcedure {
            in part :>> cart = cartridge;
            in part :>> controller = pneumatics;
            in part :>> dropletGen = generators;
            in part :>> thermal = blocks;
            in part :>> imager = imagers;
        }

        allocate sampleProcedure.intake.load.scanBarcode to rack;
        allocate sampleProcedure.intake.load.transferLoad to shuttle;

        allocate sampleProcedure.intake.prime.primeCartridge to stations;
        allocate sampleProcedure.intake.prime.primeCartridge to pneumatics;
        allocate sampleProcedure.intake.prime.reprime to stations;
        allocate sampleProcedure.intake.prime.reprime to pneumatics;
        allocate sampleProcedure.intake.prime.abortCartridge to stations;

        allocate sampleProcedure.extraction.pipette to stations;
        allocate sampleProcedure.extraction.pipette to gantry;
        allocate sampleProcedure.extraction.lysis to stations;
        allocate sampleProcedure.extraction.beadBind to stations;
        allocate sampleProcedure.extraction.washDispense1 to stations;
        allocate sampleProcedure.extraction.washDispense1 to gantry;
        allocate sampleProcedure.extraction.washCapture1 to stations;
        allocate sampleProcedure.extraction.washDispense2 to stations;
        allocate sampleProcedure.extraction.washDispense2 to gantry;
        allocate sampleProcedure.extraction.washCapture2 to stations;
        allocate sampleProcedure.extraction.elutionDispense to stations;
        allocate sampleProcedure.extraction.elutionDispense to gantry;
        allocate sampleProcedure.extraction.elute to stations;
        allocate sampleProcedure.extraction.masterMix to gantry;
        allocate sampleProcedure.extraction.masterMix to reagentStore;
        allocate sampleProcedure.extraction.transferToPartition to shuttle;

        allocate sampleProcedure.partitioning.meter to generators;
        allocate sampleProcedure.partitioning.meter to pneumatics;
        allocate sampleProcedure.partitioning.generate to generators;
        allocate sampleProcedure.partitioning.generate to pneumatics;
        allocate sampleProcedure.partitioning.regenerate to generators;
        allocate sampleProcedure.partitioning.regenerate to pneumatics;
        allocate sampleProcedure.partitioning.transferToAmplification to shuttle;

        allocate sampleProcedure.amplification.thermalCycle to blocks;
        allocate sampleProcedure.amplification.transferToReadout to shuttle;

        allocate sampleProcedure.readout.imaging to imagers;
        allocate sampleProcedure.readout.transferToWaste to shuttle;
    }
}
