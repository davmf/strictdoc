package 'System requirements' {
    requirement <'SYS-1'> 'Shift throughput' {
        @StrictDocVersioning::ItemVersion { version = 1; contentHash = "85e4a3a1209f88f1"; }
        doc /*
         * The instrument shall complete 96 samples in an 8-hour shift.
         */
    }

    requirement <'SYS-2'> 'Edited without a bump' {
        @StrictDocVersioning::ItemVersion { version = 4; contentHash = "0000000000000000"; }
        doc /*
         * The text changed after version 4.
         */
    }

    dependency from 'SYS-1' to 'STK-1' {
        @StrictDocVersioning::TracedVersion { version = 2; }
    }

    dependency from 'SYS-2' to 'STK-1' {
        @StrictDocVersioning::TracedVersion { version = 3; }
    }
}
