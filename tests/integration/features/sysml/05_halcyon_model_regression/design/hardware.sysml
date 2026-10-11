package HalcyonHardware {
    doc /*
     * Physical model of the dPCR-24 analyser (ISA-88 equipment).
     *
     * Identical units are one part with a capacity: the stations, the
     * pneumatic controllers, the droplet generators, the thermal blocks
     * and the imagers. Counts are set in the configuration (allocation
     * package and scenarios package).
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SimLib::*;

    part def SampleRack :> Resource {
        doc /* 24 sample positions and a barcode reader. */
        attribute slots : Natural = 24;
    }

    part def Shuttle :> Resource {
        doc /* XY transport of cartridges between units. One move at a time. */
        attribute strokeLength : LengthValue = 0.6 [m];
    }

    part def PipettingGantry :> Resource {
        doc /* Pipettes sample, wash, elution and master mix. Shared. */
        attribute tipCount : Natural = 8;
    }

    part def <'HW-HTR'> Heater {
        doc /* Block heater of an extraction station. */
        attribute maxTemperature : Real = 100;
    }

    part def Magnet {
        doc /* Permanent magnet for bead capture. */
        attribute fieldStrength : MagneticFluxDensityValue = 0.4 [T];
    }

    part def <'HW-STN'> ExtractionStation :> Resource {
        doc /* One station with heater and magnet. Capacity is four. */
        part heater : Heater;
        part magnet : Magnet;
    }

    part def <'HW-PNU'> PneumaticController :> Resource {
        doc /* Pressure controller that drives all on-cartridge flow. */
        attribute setPressure : PressureValue = 20000 [Pa];
    }

    part def <'HW-CART'> Cartridge {
        doc /*
         * Single-use cartridge. Channel geometry and fluid properties are
         * fixed per cartridge type.
         */
        attribute channelCount : Natural = 4;
        attribute channelDiameter : LengthValue = 0.1 [mm];
        attribute primingPathLength : LengthValue = 0.3 [m];
        attribute fluidViscosity : DynamicViscosityValue = 0.002 [Pa*s];
        attribute partitionVolume : VolumeValue = 0.017 [mL];
    }

    part def <'HW-DGN'> DropletGenerator :> Resource {
        doc /* Flow-focusing junction generator. Capacity is two. */
        attribute junctionWidth : LengthValue = 0.05 [mm];
        attribute dropletVolume : VolumeValue = 0.85e-6 [mL];
        attribute dropletFrequency : FrequencyValue = 120 [Hz];
    }

    part def <'HW-TCB'> ThermalBlock :> BatchResource {
        doc /*
         * Thermal cycler block holding four cartridges. Each batch starts
         * when four cartridges wait, or after the batch timeout.
         */
        attribute :>> batchSize = 4;
        attribute :>> batchTimeout = 10 [min];
        attribute rampRate : Real = 4;
        attribute hotStartTime : DurationValue = 5 [min];
        attribute cycles : Natural = 40;
        attribute denatureHold : DurationValue = 15 [s];
        attribute annealHold : DurationValue = 30 [s];
        attribute rampDelta : Real = 35;
    }

    part def <'HW-IMG'> FluorescenceImager :> Resource {
        doc /* Imager with one exposure per channel. Shared between cartridges. */
        attribute channels : Natural = 4;
        attribute timePerChannel : DurationValue = 45 [s];
    }

    part def <'HW-REA'> ReagentStore :> Store {
        doc /* Master mix reagent cartridges. Refilled from the reorder level. */
        attribute :>> initialLevel = 100;
        attribute :>> reorderLevel = 20;
        attribute :>> refillSize = 96;
        attribute :>> refillDuration = 15 [min];
    }

    part def WasteStore :> Store {
        doc /* Waste reservoir. Emptied by an operator. */
        attribute :>> initialLevel = 0;
    }
}
