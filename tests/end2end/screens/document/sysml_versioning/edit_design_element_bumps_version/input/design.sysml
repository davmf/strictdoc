package 'Design' {
    private import ScalarValues::*;
    private import 'Requirements'::**;

    part def Pump {
        @StrictDocVersioning::ItemVersion { version = 1; contentHash = "aeee0037b9449abe"; }
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 2;
    }

    part def Valve;
}
