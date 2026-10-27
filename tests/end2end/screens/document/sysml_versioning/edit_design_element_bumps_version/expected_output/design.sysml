package 'Design' {
    private import ScalarValues::*;
    private import 'Requirements'::**;

    part def Pump {
        @StrictDocVersioning::ItemVersion { version = 2; contentHash = "675520bd2f9810b2"; }
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 3;
        satisfy requirement 'SYS-1' by pump {
            @StrictDocVersioning::TracedVersion { version = 4; }
        }
        part pump : Pump {
            @StrictDocVersioning::ItemVersion { version = 1; contentHash = "f8e75acf2d92730f"; }
        }
    }

    part def Valve;
}
