package 'System requirements' {
    private import 'Stakeholder requirements'::**;

    requirement <'SYS-1'> 'Shift throughput' {
        @StrictDocVersioning::ItemVersion { version = 2; contentHash = "85e4a3a1209f88f1"; }
        doc /*
         * The instrument shall complete 96 samples in an 8-hour shift.
         */
    }

    dependency from 'SYS-1' to 'STK-1' {
        @StrictDocVersioning::TracedVersion { version = 2; }
    }
}
