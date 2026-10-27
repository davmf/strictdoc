package 'Design' {
    private import 'System requirements'::**;

    part def Pump {
        doc /*
         * The pump moves sample into the chip.
         */
        satisfy 'SYS-1' by pump {
            @StrictDocVersioning::TracedVersion { version = 1; }
        }
        part pump : Pump;
    }
}
