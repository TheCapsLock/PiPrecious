import uuid

from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.signals import pre_delete, post_delete
from django.dispatch.dispatcher import receiver
from exodus_core.analysis.static_analysis import *


class Device(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    created = models.DateTimeField(auto_now_add = True)
    updated = models.DateTimeField(auto_now = True)
    name = models.CharField(max_length = 200, unique = True)
    description = models.TextField(blank = True)
    brand = models.CharField(max_length = 200)
    version = models.CharField(max_length = 200, blank = True)
    serial = models.CharField(max_length = 200, blank = False, unique = True)
    label = models.CharField(max_length = 200, blank = True)
    website = models.URLField(blank = True)
    raw_parameters = models.TextField(blank = True)
    rules = models.TextField(blank = True, null = True)

    def __str__(self):
        return self.name

    def short(self):
        return self.name[:2]

    class Meta:
        ordering = ('name',)
        verbose_name_plural = "devices"


def path_and_rename(instance, filename):
    return '%s_%s' % (instance.id, filename)


class File(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    created = models.DateTimeField(auto_now_add = True)
    updated = models.DateTimeField(auto_now = True)
    name = models.CharField(max_length = 200)
    sha256 = models.CharField(max_length = 200, blank = True, unique = True)
    size = models.IntegerField(blank = True)
    file = models.FileField(upload_to = path_and_rename)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk:
            size = 0
            sha = hashlib.sha256()
            for chunk in self.file.chunks():
                sha.update(chunk)
                size += len(chunk)
            self.sha256 = sha.hexdigest()
            self.size = size
        super(File, self).save(*args, **kwargs)

    class Meta:
        ordering = ('name',)
        verbose_name_plural = "files"


class IoTDevice(Device):
    class Meta:
        ordering = ('name',)
        verbose_name_plural = "IoT devices"


class Smartphone(Device):
    imei = models.CharField(max_length = 200, blank = True, unique = True)
    phone_number = models.CharField(max_length = 200, blank = True, unique = True)

    class Meta:
        ordering = ('name',)
        verbose_name_plural = "Smartphones"


class APKFile(File):
    class Meta:
        ordering = ('name',)
        verbose_name_plural = "APK files"


class PCAPFile(File):
    class Meta:
        ordering = ('name',)
        verbose_name_plural = "PCAP files"


class FlowFile(File):
    class Meta:
        ordering = ('name',)
        verbose_name_plural = "FLOW files"


class BluetoothDump(File):
    class Meta:
        ordering = ('name',)
        verbose_name_plural = "Bluetooth dumps"


@receiver(pre_delete, sender = File)
def file_model_delete(sender, instance, **kwargs):
    instance.file.delete(False)


class Application(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    name = models.CharField(max_length = 200, blank = True, default = 'application')
    created = models.DateTimeField(auto_now_add = True)
    updated = models.DateTimeField(auto_now = True)
    apk = models.OneToOneField(APKFile, on_delete = models.CASCADE)
    handle = models.CharField(max_length = 200, blank = True)
    version_code = models.IntegerField(blank = True)
    version_name = models.CharField(max_length = 200, blank = True)
    icon_phash = models.IntegerField(blank = True, null = True)
    app_uid = models.CharField(max_length = 200, blank = True)
    creator = models.CharField(max_length = 200, blank = True)
    rules = models.TextField(blank = True, null = True)

    def __str__(self):
        return self.name

    def create_rules(self):
        rules = 'rule application_handle: application handle {\n\tstrings:\n\t\t$h = "%s"\n\tcondition:\n\t\t$h\n}\n' % self.handle
        rules += 'rule application_version: application version {\n\tstrings:\n\t\t$ = "%s"\n\t\t$ = "%s"\n\tcondition:\n\t\tany of them\n}\n' % (
        self.version_name, self.version_code)
        self.rules = rules

    def save(self, *args, **kwargs):
        with tempfile.NamedTemporaryFile(delete = True) as apk:
            for chunk in self.apk.file.chunks():
                apk.write(chunk)
            apk.seek(0)
            print(apk.name)
            try:
                sa = StaticAnalysis(apk.name)
                self.handle = sa.get_package()
                self.version_code = sa.get_version_code()
                self.version_name = sa.get_version()
                self.name = '%s - %s' % (sa.get_app_name(), self.version_name)
                self.app_uid = sa.get_application_universal_id()
            except Exception as e:
                logging.error(e)
            finally:
                if len(self.rules.strip()) == 0:
                    self.create_rules()
                super(Application, self).save(*args, **kwargs)

    class Meta:
        ordering = ('name',)
        verbose_name_plural = "Applications"


class Experiment(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    created = models.DateTimeField(auto_now_add = True)
    updated = models.DateTimeField(auto_now = True)
    name = models.CharField(max_length = 200)
    description = models.TextField(blank = True)
    application = models.ForeignKey(Application, on_delete = models.CASCADE, blank = True, null = True)
    iot_device = models.ForeignKey(IoTDevice, on_delete = models.CASCADE, blank = True, null = True)
    smartphone = models.ForeignKey(Smartphone, on_delete = models.CASCADE, blank = True, null = True)
    rules = models.TextField(blank = True, null = True)
    report = JSONField(blank = True, null = True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name_plural = "Experiments"


class Session(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    created = models.DateTimeField(auto_now_add = True)
    updated = models.DateTimeField(auto_now = True)
    name = models.CharField(max_length = 200)
    description = models.TextField(blank = True)
    experiment = models.ForeignKey(Experiment, on_delete = models.CASCADE)
    pcap_file = models.ForeignKey(PCAPFile, on_delete = models.CASCADE, blank = True, null = True)
    flow_file = models.ForeignKey(FlowFile, on_delete = models.CASCADE, blank = True, null = True)
    bluetooth_dump = models.ForeignKey(BluetoothDump, on_delete = models.CASCADE, blank = True, null = True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('created',)
        verbose_name_plural = "Sessions"


@receiver(post_delete, sender = Session)
def session_model_delete(sender, instance, **kwargs):
    if instance.pcap_file is not None:
        instance.pcap_file.delete(False)
    if instance.flow_file is not None:
        instance.flow_file.delete(False)
    if instance.bluetooth_dump is not None:
        instance.bluetooth_dump.delete(False)


# class Domain(models.Model):
#     name = models.CharField(primary_key = True, max_length = 200, editable = False)
#     is_tracker = models.BooleanField(default = False)
#
#     def __str__(self):
#         return self.name
#
#
# class IpAddress(models.Model):
#     address = models.CharField(primary_key = True, max_length = 200, editable = False)
#     domain = models.ForeignKey(Domain, on_delete = models.CASCADE, blank = True, null = True)
#     country = models.CharField(default = '', max_length = 200, blank = True)
#     country_code = models.CharField(default = '', max_length = 200, blank = True)
#     city = models.CharField(default = '', max_length = 200, blank = True)
#     region = models.CharField(default = '', max_length = 200, blank = True)
#     latitude = models.CharField(default = '', max_length = 200, blank = True)
#     longitude = models.CharField(default = '', max_length = 200, blank = True)
#     organization = models.CharField(default = '', max_length = 200, blank = True)
#
#     def __str__(self):
#         return self.address


class NetworkAnalysis(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    session = models.ForeignKey(Session, on_delete = models.CASCADE)

    class Meta:
        verbose_name_plural = "Network analyses"


class DNSQuery(models.Model):
    id = models.UUIDField(primary_key = True, default = uuid.uuid4, editable = False)
    network_analysis = models.ForeignKey(NetworkAnalysis, on_delete = models.CASCADE)
    address = models.CharField(default = '', max_length = 200, editable = False)
    domain = models.CharField(default = '', max_length = 200, blank = True)
    country = models.CharField(default = '', max_length = 200, blank = True)
    country_code = models.CharField(default = '', max_length = 200, blank = True)
    city = models.CharField(default = '', max_length = 200, blank = True)
    region = models.CharField(default = '', max_length = 200, blank = True)
    latitude = models.CharField(default = '', max_length = 200, blank = True)
    longitude = models.CharField(default = '', max_length = 200, blank = True)
    organization = models.CharField(default = '', max_length = 200, blank = True)

    class Meta:
        ordering = ('domain',)
        verbose_name_plural = "DNS queries"

    def __str__(self):
        return '%s - %s' % (self.domain, self.address)
