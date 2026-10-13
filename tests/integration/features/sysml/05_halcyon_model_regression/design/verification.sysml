package HalcyonVerification {
    doc /*
     * Verification cases. Each SYS requirement has one case. Simulated
     * metrics use SimulationVerification from SimLib. Design checks use
     * ModelCheck, which compares the observed design value with the
     * requirement's measured attribute. The satisfy statements link design
     * elements to each SYS requirement.
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import SimLib::*;
    private import HalcyonHardware::*;
    private import HalcyonWorkflow::*;
    private import HalcyonAllocation::*;
    private import HalcyonScenarios::*;
    private import HalcyonPhysics::*;
    private import 'Halcyon dPCR-24 system requirements'::**;

    verification def ModelCheck {
        doc /* Compares a design value with the requirement's measured attribute. */
        attribute observed;
    }


    satisfy 'SYS-THR-001' by baseSteady.configuration;
    satisfy 'SYS-THR-001' by baseSteady.configuration.cartridge;
    satisfy 'SYS-UTL-001' by baseSteady.configuration.imagers;
    satisfy 'SYS-TAT-001' by baseBatch.configuration;
    satisfy 'SYS-TAT-002' by baseSteady.configuration;
    satisfy 'SYS-TAT-003' by baseSteady.configuration;
    satisfy 'SYS-VAL-001' by baseSteady.configuration.cartridge;
    satisfy 'SYS-VAL-002' by baseSteady.configuration;
    satisfy 'SYS-DRP-001' by baseSteady.configuration.generators;
    satisfy 'SYS-DRP-001' by baseSteady.configuration.cartridge;
    satisfy 'SYS-LYS-001' by baseSteady.configuration.stations.heater;
    satisfy 'SYS-CH-001' by baseSteady.configuration.cartridge;
    satisfy 'SYS-OPS-001' by baseSteady.configuration.reagentStore;
    satisfy 'SYS-STAT-001' by baseSteady.configuration;

    verification verSysThr001 : SimulationVerification {
        doc /* Completed samples per 8-hour shift at nominal load. */
        objective { verify 'SYS-THR-001'; }
        attribute :>> measured = 'SYS-THR-001'.measuredSamplesPerShift;
        attribute :>> metric = MetricKind::completedPerShift;
        attribute :>> horizon = 8 [h];
        ref part :>> scenario = baseSteady;
    }

    verification verSysUtl001 : SimulationVerification {
        doc /* Mean imager utilisation at nominal load. */
        objective { verify 'SYS-UTL-001'; }
        attribute :>> measured = 'SYS-UTL-001'.measuredImagerUtilisation;
        attribute :>> metric = MetricKind::utilisation;
        ref part :>> scenario = baseSteady;
        ref part :>> resource = baseSteady.configuration.imagers;
    }

    verification verSysTat001 : SimulationVerification {
        doc /* First result of the 24-sample batch loaded at shift start. */
        objective { verify 'SYS-TAT-001'; }
        attribute :>> measured = 'SYS-TAT-001'.measuredTimeToFirstResult;
        attribute :>> metric = MetricKind::timeToFirstResult;
        attribute :>> horizon = 3 [h];
        ref part :>> scenario = baseBatch;
    }

    verification verSysTat002 : SimulationVerification {
        doc /* Mean turnaround at nominal load. */
        objective { verify 'SYS-TAT-002'; }
        attribute :>> measured = 'SYS-TAT-002'.measuredMeanTurnaround;
        attribute :>> metric = MetricKind::meanTurnaround;
        attribute :>> horizon = 16 [h];
        ref part :>> scenario = baseSteady;
    }

    verification verSysTat003 : SimulationVerification {
        doc /* Mean turnaround of STAT samples at nominal load. */
        objective { verify 'SYS-TAT-003'; }
        attribute :>> measured = 'SYS-TAT-003'.measuredMeanStatTurnaround;
        attribute :>> metric = MetricKind::meanStatTurnaround;
        attribute :>> horizon = 16 [h];
        ref part :>> scenario = baseSteady;
    }

    verification verSysVal001 : SimulationVerification {
        doc /* Invalid results after reflex retesting at nominal load. */
        objective { verify 'SYS-VAL-001'; }
        attribute :>> measured = 'SYS-VAL-001'.measuredInvalidRate;
        attribute :>> metric = MetricKind::invalidRate;
        attribute :>> horizon = 16 [h];
        ref part :>> scenario = baseSteady;
    }

    verification verSysVal002 : ModelCheck {
        doc /* Reflex retests configured per invalid run. */
        objective { verify 'SYS-VAL-002'; }
        attribute :>> observed = baseSteady.configuration.maxRetests;
    }

    verification verSysDrp001 : ModelCheck {
        doc /* Droplets per channel from partition volume and droplet volume. */
        objective { verify 'SYS-DRP-001'; }
        attribute :>> observed = DropletCount(partitionVolume = baseSteady.configuration.cartridge.partitionVolume, dropletVolume = baseSteady.configuration.generators.dropletVolume);
    }

    verification verSysLys001 : ModelCheck {
        doc /* Heater maximum set point against the lysis temperature. */
        objective { verify 'SYS-LYS-001'; }
        attribute :>> observed = baseSteady.configuration.stations.heater.maxTemperature;
    }

    verification verSysCh001 : ModelCheck {
        doc /* Channels per cartridge. */
        objective { verify 'SYS-CH-001'; }
        attribute :>> observed = baseSteady.configuration.cartridge.channelCount;
    }

    verification verSysOps001 : ModelCheck {
        doc /* Hours of master mix at the nominal arrival rate, from the reagent store. */
        objective { verify 'SYS-OPS-001'; }
        attribute :>> observed = baseSteady.configuration.reagentStore.initialLevel / 12;
    }

    verification verSysStat001 : ModelCheck {
        doc /* Priority levels used by work items (routine and STAT). */
        objective { verify 'SYS-STAT-001'; }
        attribute :>> observed = 2;
    }
}
