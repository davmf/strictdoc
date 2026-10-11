package HalcyonPhysics {
    doc /*
     * Step physics as calc defs over part attributes. No external solver.
     * Units are SI. Values are evaluated by the simulation generator.
     */

    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;

    calc def ChannelVolume {
        doc /* Volume of a cylindrical channel: pi d^2 L / 4. */
        in diameter : LengthValue;
        in length : LengthValue;
        return : VolumeValue = 3.14159265 * diameter * diameter * length / 4;
    }

    calc def HagenPoiseuilleFlow {
        doc /* Volume flow rate of laminar flow: pi d^4 dP / (128 mu L). */
        in pressure : PressureValue;
        in viscosity : DynamicViscosityValue;
        in length : LengthValue;
        in diameter : LengthValue;
        return : VolumeFlowRateValue = 3.14159265 * diameter * diameter * diameter * diameter * pressure / (128 * viscosity * length);
    }

    calc def PrimingTime {
        doc /* Time to fill the priming channel: channel volume / flow rate. */
        in pressure : PressureValue;
        in viscosity : DynamicViscosityValue;
        in length : LengthValue;
        in diameter : LengthValue;
        return : DurationValue = ChannelVolume(diameter, length) / HagenPoiseuilleFlow(pressure, viscosity, length, diameter);
    }

    calc def DropletCount {
        doc /* Droplets per channel: partition volume / droplet volume. */
        in partitionVolume : VolumeValue;
        in dropletVolume : VolumeValue;
        return : Real = partitionVolume / dropletVolume;
    }

    calc def DropletGenerationTime {
        doc /* Volume per channel / (droplet volume * generation frequency). */
        in partitionVolume : VolumeValue;
        in dropletVolume : VolumeValue;
        in frequency : FrequencyValue;
        return : DurationValue = partitionVolume / (dropletVolume * frequency);
    }

    calc def ThermalRunTime {
        doc /*
         * Hot start, then cycles of denature hold, anneal hold and two
         * ramps. The ramp rate is the block's rate in kelvin per second.
         */
        in hotStart : DurationValue;
        in cycles : Natural;
        in denatureHold : DurationValue;
        in annealHold : DurationValue;
        in rampDelta : Real;
        in rampRate : Real;
        return : DurationValue = hotStart + cycles * (denatureHold + annealHold + 2 * rampDelta / rampRate);
    }

    calc def ImagingTime {
        doc /* Imaging all channels of one cartridge, one after another. */
        in channels : Natural;
        in timePerChannel : DurationValue;
        return : DurationValue = channels * timePerChannel;
    }
}
