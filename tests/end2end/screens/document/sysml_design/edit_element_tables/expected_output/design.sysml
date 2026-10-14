package 'Design' {
    // Line notes outside the edited element are kept.
    part def Pump {
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 4 [l/min];
        satisfy 'SYS-THR-001' by pump;
        part pump : Pump;
        part valve : Valve;
    }

    part def Valve;

    verification def ThroughputCheck {
        objective {
            verify 'SYS-THR-001';
        }
    }
}
