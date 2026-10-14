package 'Design' {
    part def Pump {
        satisfy 'SYS-THR-001' by pump;
        part pump : Pump;
    }
}
