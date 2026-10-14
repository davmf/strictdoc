package 'Design' {
    // Line notes outside the edited element are kept.
    part def Pump {
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 2;
        attribute obsolete : Real;
        satisfy 'SYS-THR-001' by pump;
        part pump : Pump;
    }

    part def Valve;

    verification def ThroughputCheck {
        objective {
            verify 'SYS-THR-001';
        }
    }
}
