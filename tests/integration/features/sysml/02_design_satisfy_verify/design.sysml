package 'Design' {
    part def Pump {
        doc /*
         * The pump moves sample into the chip.
         */
        attribute flowRate : Real = 2;
        satisfy 'SYS-THR-001' by pump;
        part pump : Pump;
    }

    verification def ThroughputCheck {
        objective {
            verify 'SYS-THR-001';
        }
    }
}
