package 'Design' {
    part def Pump {
        @StrictDocVersioning::ItemVersion { version = 2; contentHash = "670569fe3929eb4d"; }
        doc /*
         * The pump moves sample into the chip.
         */
        satisfy 'SYS-1' by pump {
            @StrictDocVersioning::TracedVersion { version = 1; }
        }
        satisfy 'SYS-2' by pump {
            @StrictDocVersioning::TracedVersion { version = 3; }
        }
        part pump : Pump;
    }
}
