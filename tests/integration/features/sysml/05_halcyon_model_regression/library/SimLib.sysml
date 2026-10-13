package SimLib {
    doc /*
     * Generic discrete-event simulation vocabulary.
     *
     * Project independent. The generator reads any model that imports
     * this package. Read only in StrictDoc.
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;

    attribute def Probability :> Real;

    enum def DistributionKind { enum fixed; enum triangular; enum normal; enum logNormal; }

    enum def MetricKind { enum completedPerShift; enum timeToFirstResult; enum meanTurnaround; enum meanStatTurnaround; enum invalidRate; enum utilisation; }

    calc def Bernoulli {
        doc /* Random branch: true with probability p. */
        in p : Probability;
        return : Boolean;
    }

    abstract part def Resource {
        attribute capacity : Natural default 1;
    }

    abstract part def BatchResource :> Resource {
        attribute batchSize : Natural default 1;
        attribute batchTimeout : DurationValue default 0 [s];
    }

    abstract part def Store {
        attribute initialLevel : Natural default 0;
        attribute reorderLevel : Natural default 0;
        attribute refillSize : Natural default 0;
        attribute refillDuration : DurationValue default 0 [s];
    }

    abstract item def WorkItem {
        attribute priority : Natural default 0;
    }

    action def Step {
        attribute distribution : DistributionKind default DistributionKind::fixed;
        attribute nominal : DurationValue;
        attribute low : DurationValue;
        attribute high : DurationValue;
        attribute sd : DurationValue;
        attribute sigma : Real;
        attribute consumes : Natural default 0;
        attribute retest : Boolean default false;
    }

    abstract attribute def ArrivalProcess {
        attribute statFraction : Probability default 0;
    }

    attribute def BatchArrival :> ArrivalProcess {
        attribute count : Natural;
        attribute time : DurationValue default 0 [s];
    }

    attribute def PoissonArrival :> ArrivalProcess {
        attribute rate : FrequencyValue;
    }

    abstract part def Configuration {
        attribute maxRetests : Natural default 1;
    }

    abstract part def Scenario {
        attribute arrivals : ArrivalProcess;
        attribute warmUpTime : DurationValue default 0 [h];
        part configuration : Configuration;
    }

    verification def SimulationVerification {
        attribute measured;
        attribute metric : MetricKind;
        attribute horizon : DurationValue default 8 [h];
        attribute replications : Natural default 10;
        attribute confidence : Probability default 0.95;
        ref part scenario : Scenario;
        ref part resource : Resource [0..1];
    }
}
