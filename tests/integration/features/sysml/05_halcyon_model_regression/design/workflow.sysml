package HalcyonWorkflow {
    doc /*
     * ISA-88 procedural model for one sample. The procedure has five unit
     * procedures (intake, extraction, partitioning, amplification,
     * readout). Each unit procedure has operations, and each operation has
     * phases, which are Steps. Equipment is bound in the allocation
     * package. A cartridge that aborts or yields an invalid result goes
     * to a retest step (retest = true).
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SimLib::*;
    private import HalcyonPhysics::*;
    private import HalcyonHardware::*;

    item def Sample :> WorkItem {
        attribute invalid : Boolean default false;
    }

    action def <'WF-PROC'> SampleProcedure {
        in item sample : Sample;
        in part cart : Cartridge;
        in part controller : PneumaticController;
        in part dropletGen : DropletGenerator;
        in part thermal : ThermalBlock;
        in part imager : FluorescenceImager;
        attribute pBubble : Probability = 0.05;
        attribute pLowDroplets : Probability = 0.03;

        action intake {
            action load {
                action scanBarcode : Step { :>> nominal = 10 [s]; }
                action transferLoad : Step { :>> nominal = 30 [s]; }
                first scanBarcode then transferLoad;
            }
            action prime {
                action primeCartridge : Step {
                    :>> nominal = PrimingTime(pressure = controller.setPressure, viscosity = cart.fluidViscosity, length = cart.primingPathLength, diameter = cart.channelDiameter);
                }
                action reprime : Step {
                    :>> distribution = DistributionKind::triangular;
                    :>> low = 20 [s];
                    :>> nominal = 30 [s];
                    :>> high = 40 [s];
                }
                action abortCartridge : Step { :>> nominal = 10 [s]; }
                action abortRetest : Step {
                    :>> nominal = 0 [s];
                    :>> retest = true;
                }
                decide bubble1;
                decide bubble2;
                merge primed;
                first primeCartridge then bubble1;
                first bubble1 if Bernoulli(p = pBubble) then reprime;
                first bubble1 if not Bernoulli(p = pBubble) then primed;
                first reprime then bubble2;
                first bubble2 if Bernoulli(p = pBubble) then abortCartridge;
                first bubble2 if not Bernoulli(p = pBubble) then primed;
                first abortCartridge then abortRetest;
            }
            first load then prime;
        }

        action extraction {
            action pipette : Step { :>> nominal = 60 [s]; }
            action lysis : Step { :>> nominal = 360 [s]; }
            action beadBind : Step { :>> nominal = 180 [s]; }
            action washDispense1 : Step { :>> nominal = 20 [s]; }
            action washCapture1 : Step { :>> nominal = 130 [s]; }
            action washDispense2 : Step { :>> nominal = 20 [s]; }
            action washCapture2 : Step { :>> nominal = 130 [s]; }
            action elutionDispense : Step { :>> nominal = 20 [s]; }
            action elute : Step { :>> nominal = 240 [s]; }
            action masterMix : Step {
                :>> nominal = 40 [s];
                :>> consumes = 1;
            }
            action transferToPartition : Step { :>> nominal = 30 [s]; }
            fork split;
            join joined;
            first pipette then lysis;
            first lysis then beadBind;
            first beadBind then washDispense1;
            first washDispense1 then washCapture1;
            first washCapture1 then washDispense2;
            first washDispense2 then washCapture2;
            first washCapture2 then split;
            first split then elutionDispense;
            first elutionDispense then elute;
            first split then masterMix;
            first elute then joined;
            first masterMix then joined;
            first joined then transferToPartition;
        }

        action partitioning {
            action meter : Step { :>> nominal = 30 [s]; }
            action generate : Step {
                :>> nominal = DropletGenerationTime(partitionVolume = cart.partitionVolume, dropletVolume = dropletGen.dropletVolume, frequency = dropletGen.dropletFrequency);
            }
            action regenerate : Step {
                :>> nominal = DropletGenerationTime(partitionVolume = cart.partitionVolume, dropletVolume = dropletGen.dropletVolume, frequency = dropletGen.dropletFrequency);
            }
            action markInvalid : Step { :>> nominal = 0 [s]; }
            action transferToAmplification : Step { :>> nominal = 30 [s]; }
            decide lowCount1;
            decide lowCount2;
            merge partitioned;
            first meter then generate;
            first generate then lowCount1;
            first lowCount1 if Bernoulli(p = pLowDroplets) then regenerate;
            first lowCount1 if not Bernoulli(p = pLowDroplets) then partitioned;
            first regenerate then lowCount2;
            first lowCount2 if Bernoulli(p = pLowDroplets) then markInvalid;
            first lowCount2 if not Bernoulli(p = pLowDroplets) then partitioned;
            first markInvalid then partitioned;
            first partitioned then transferToAmplification;
        }

        action amplification {
            action thermalCycle : Step {
                :>> nominal = ThermalRunTime(hotStart = thermal.hotStartTime, cycles = thermal.cycles, denatureHold = thermal.denatureHold, annealHold = thermal.annealHold, rampDelta = thermal.rampDelta, rampRate = thermal.rampRate);
            }
            action transferToReadout : Step { :>> nominal = 30 [s]; }
            first thermalCycle then transferToReadout;
        }

        action readout {
            action imaging : Step {
                :>> nominal = ImagingTime(channels = imager.channels, timePerChannel = imager.timePerChannel);
            }
            action poissonAnalysis : Step { :>> nominal = 60 [s]; }
            action report : Step { :>> nominal = 0 [s]; }
            action reflexRetest : Step {
                :>> nominal = 0 [s];
                :>> retest = true;
            }
            action transferToWaste : Step { :>> nominal = 30 [s]; }
            decide invalidCheck;
            first imaging then poissonAnalysis;
            first poissonAnalysis then invalidCheck;
            first invalidCheck if sample.invalid then reflexRetest;
            first invalidCheck if not sample.invalid then report;
            first report then transferToWaste;
        }

        first intake then extraction;
        first extraction then partitioning;
        first partitioning then amplification;
        first amplification then readout;
    }
}
