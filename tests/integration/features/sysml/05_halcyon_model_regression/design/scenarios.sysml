package HalcyonScenarios {
    doc /*
     * Configurations and scenarios of the analyser.
     *
     * Base: two thermal blocks, one imager, one batch of 24 at shift start.
     * SteadyStat: base configuration, Poisson arrivals at 12 per hour, 10%
     * STAT. HighThroughput: three thermal blocks, two imagers, same arrivals
     * as SteadyStat.
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SimLib::*;
    private import HalcyonHardware::*;
    private import HalcyonAllocation::*;

    part def BaseInstrument :> Instrument {
        part :>> stations {
            attribute :>> capacity = 4;
        }
        part :>> pneumatics {
            attribute :>> capacity = 2;
        }
        part :>> generators {
            attribute :>> capacity = 2;
        }
        part :>> blocks {
            attribute :>> capacity = 2;
        }
        part :>> imagers {
            attribute :>> capacity = 1;
        }
    }

    part def HighThroughputInstrument :> Instrument {
        part :>> stations {
            attribute :>> capacity = 4;
        }
        part :>> pneumatics {
            attribute :>> capacity = 2;
        }
        part :>> generators {
            attribute :>> capacity = 2;
        }
        part :>> blocks {
            attribute :>> capacity = 3;
        }
        part :>> imagers {
            attribute :>> capacity = 2;
        }
    }

    part def BaseBatch :> Scenario {
        part :>> configuration : BaseInstrument;
        attribute :>> arrivals : BatchArrival {
            :>> count = 24;
            :>> time = 0 [s];
        }
    }

    part def BaseSteadyStat :> Scenario {
        part :>> configuration : BaseInstrument;
        attribute :>> arrivals : PoissonArrival {
            :>> rate = 12 [1/h];
            :>> statFraction = 0.1;
        }
        attribute :>> warmUpTime = 1 [h];
    }

    part def HighThroughputSteadyStat :> Scenario {
        part :>> configuration : HighThroughputInstrument;
        attribute :>> arrivals : PoissonArrival {
            :>> rate = 12 [1/h];
            :>> statFraction = 0.1;
        }
        attribute :>> warmUpTime = 1 [h];
    }

    part baseBatch : BaseBatch;
    part baseSteady : BaseSteadyStat;
    part highThroughput : HighThroughputSteadyStat;
}
